#!/usr/bin/env bash
# Fmax / utilisation / power sweep for the Lumberjack accelerator.
#
#   ./fpga/sweep.sh                 # run everything in the manifest
#   JOBS=2 ./fpga/sweep.sh          # limit concurrency (each Vivado run wants ~4-8 GB)
#   MANIFEST=other.yml ./fpga/sweep.sh
#   ./fpga/sweep.sh --harvest-only  # re-parse existing results without rebuilding
#
# Reads fpga/sweep.yml, crosses parts x configs, runs each combination through
# fpga/bench_synth.tcl in parallel, then harvests every report into
# results/sweep_summary.yml.

set -euo pipefail

MANIFEST="${MANIFEST:-fpga/sweep.yml}"
JOBS="${JOBS:-4}"
TCL="${TCL:-fpga/bench_synth.tcl}"
RESULTS_DIR="${RESULTS_DIR:-results}"
LOG_DIR="${LOG_DIR:-logs}"

HARVEST_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --harvest-only) HARVEST_ONLY=1 ;;
        *) echo "unknown argument: $arg" >&2; exit 2 ;;
    esac
done

# ---------------------------------------------------------------------------
# Run identity, shared with the simulation pipeline so FPGA and sim results
# from the same source tree can be reconciled.
# ---------------------------------------------------------------------------
GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo nogit)
git diff --quiet 2>/dev/null || GIT_SHA="${GIT_SHA}-dirty"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-${GIT_SHA}}"
export RUN_ID

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
for tool in yq parallel vivado; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "error: '$tool' not found in PATH" >&2
        exit 1
    }
done

[ -f "$MANIFEST" ] || { echo "error: manifest '$MANIFEST' not found" >&2; exit 1; }
[ -f "$TCL" ]      || { echo "error: tcl script '$TCL' not found" >&2; exit 1; }

mkdir -p "$LOG_DIR" "$RESULTS_DIR"

# ---------------------------------------------------------------------------
# Expand the manifest into one TSV row per job:
#   name  part  period_ns  cells  superscalar  cache_size
#
# period_ns and cell_cache_size resolve per-part, falling back to .defaults.
# ---------------------------------------------------------------------------
expand_manifest() {
    yq -r '
      .defaults.period_ns       as $dperiod |
      .defaults.cell_cache_size as $dcache  |
      .parts   as $parts |
      .configs as $cfgs  |
      $parts | to_entries | .[] as $p |
      $cfgs  | to_entries | .[] as $c |
      [ ($p.key + "_" + $c.key),
        $p.value.part,
        ($p.value.period_ns       // $dperiod),
        $c.value.cells,
        $c.value.superscalar,
        ($c.value.cell_cache_size // $p.value.cell_cache_size // $dcache)
      ] | @tsv
    ' "$MANIFEST"
}

# ---------------------------------------------------------------------------
# Report parsing. Vivado's row labels drift between versions, so every getter
# degrades to "null" rather than aborting the harvest.
# ---------------------------------------------------------------------------

power_field() {
    local file="$1" label="$2"
    [ -f "$file" ] || { echo "null"; return; }
    awk -F'|' -v lbl="$label" '
        index($2, lbl) {
            gsub(/^[ \t]+|[ \t]+$/, "", $3)
            if ($3 != "") { print $3; found = 1; exit }
        }
        END { if (!found) print "null" }
    ' "$file"
}

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
if [ "$HARVEST_ONLY" -eq 0 ]; then
    njobs=$(expand_manifest | wc -l)
    echo "run id : $RUN_ID"
    echo "manifest: $MANIFEST"
    echo "jobs    : $njobs across $JOBS workers"
    echo

    # --halt never: one failing configuration should not abandon the sweep.
    # The joblog records exit codes so failures are visible afterwards.
    expand_manifest |
    parallel --colsep '\t' -j"$JOBS" --bar --halt never \
             --joblog "$LOG_DIR/sweep.joblog" \
      "vivado -mode batch -nojournal -nolog -source $TCL \
         -tclargs {2} {3} $RESULTS_DIR/{1} {4} {5} {6} \
         > $LOG_DIR/{1}.log 2>&1" \
      || echo "note: one or more jobs failed; see $LOG_DIR/sweep.joblog"

    echo
fi

# ---------------------------------------------------------------------------
# Harvest
# ---------------------------------------------------------------------------
SUMMARY="$RESULTS_DIR/sweep_summary.yml"

{
    echo "run_id: $RUN_ID"
    echo "git_sha: $GIT_SHA"
    echo "manifest: $MANIFEST"
    echo "generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "runs:"

    while IFS=$'\t' read -r name part period cells ss cache; do
        d="$RESULTS_DIR/$name"

        echo "  $name:"
        echo "    part: $part"
        echo "    cells: $cells"
        echo "    superscalar: $ss"
        echo "    cell_cache_size: $cache"
        echo "    target_period_ns: $period"

        if [ ! -d "$d" ]; then
            echo "    status: missing"
            continue
        fi

        # ---- timing ----
        # The summary block is columnar, not pipe-delimited: the WNS value sits
        # two lines below the "WNS(ns)" header (header, dashes, values).
        wns=$(awk '/WNS\(ns\)/ { getline; getline; print $1; exit }' \
              "$d/timing.rpt" 2>/dev/null || true)
        [ -n "$wns" ] || wns="null"

        echo "    wns_ns: $wns"
        if [ "$wns" != "null" ] && [ "$wns" != "NA" ]; then
            fmax=$(awk -v p="$period" -v w="$wns" \
                   'BEGIN { d = p - w; if (d > 0) printf "%.2f", 1000.0 / d; else print "null" }')
            echo "    fmax_mhz: $fmax"
        else
            echo "    fmax_mhz: null"
        fi

        # ---- utilisation (written by the tcl as a flat key: value file) ----
        if [ -f "$d/resources.yml" ]; then
            sed 's/^/    /' "$d/resources.yml"
        else
            echo "    luts: null"
            echo "    lutram: null"
            echo "    ffs: null"
            echo "    brams: null"
            echo "    dsps: null"
        fi

        # ---- power ----
        echo "    power_total_w: $(power_field   "$d/power.rpt" 'Total On-Chip Power')"
        echo "    power_dynamic_w: $(power_field "$d/power.rpt" 'Dynamic (W)')"
        echo "    power_static_w: $(power_field  "$d/power.rpt" 'Device Static (W)')"

        if [ -f "$d/power.rpt" ]; then
            conf=$(power_field "$d/power.rpt" 'Confidence Level')
            echo "    power_confidence: ${conf:-null}"
        fi

        # ---- status ----
        if [ -f "$d/timing.rpt" ] && [ -f "$d/utilization.rpt" ]; then
            echo "    status: ok"
        else
            echo "    status: incomplete"
        fi

    done < <(expand_manifest)

} > "$SUMMARY"

echo "wrote $SUMMARY"
echo

# ---------------------------------------------------------------------------
# Human-readable table
# ---------------------------------------------------------------------------
{
    printf 'config\tfmax_mhz\twns_ns\tluts\tlutram\tffs\tbram\tdsp\tpower_w\n'
    yq -r '
      .runs | to_entries | .[] |
      [ .key,
        (.value.fmax_mhz        // "-"),
        (.value.wns_ns          // "-"),
        (.value.luts            // "-"),
        (.value.lutram          // "-"),
        (.value.ffs             // "-"),
        (.value.brams           // "-"),
        (.value.dsps            // "-"),
        (.value.power_total_w   // "-")
      ] | @tsv
    ' "$SUMMARY"
} | column -t

echo
if [ -f "$LOG_DIR/sweep.joblog" ]; then
    failed=$(awk 'NR > 1 && $7 != 0 { print $NF }' "$LOG_DIR/sweep.joblog" | wc -l)
    if [ "$failed" -gt 0 ]; then
        echo "warning: $failed job(s) exited non-zero -- check $LOG_DIR/"
    fi
fi