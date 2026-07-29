# Out-of-context synthesis + implementation for Fmax / utilisation benchmarking.
#
# vivado -mode batch -nojournal -nolog -source fpga/bench_synth.tcl \
#        -tclargs <part> <period_ns> <outdir> <cells> <superscalar>

set part      [lindex $argv 0]
set period    [lindex $argv 1]
set outdir    [lindex $argv 2]
set cells     [lindex $argv 3]
set superscal [lindex $argv 4]

file mkdir $outdir

# Limit per-run threading so concurrent sweep jobs do not oversubscribe.
set_param general.maxThreads 4

create_project -in_memory -part $part

# ---- Sources -----------------------------------------------------------------
set fp [open "./lumberjack.f" r]
set srcs [list]
while {[gets $fp line] >= 0} {
    if {[string trim $line] eq "" || [string match "#*" $line]} { continue }
    lappend srcs $line
}
close $fp
add_files -norecurse $srcs

# ---- Constraints -------------------------------------------------------------
# Added as a file: there is no design open yet, so create_clock cannot be called
# directly at this point.

set xdc_path "$outdir/bench_ooc.xdc"
set xfh [open $xdc_path w]
puts $xfh "create_clock -period $period -name sys_clk \[get_ports clk\]"
puts $xfh ""
# puts $xfh "# Boundary paths are not what this benchmark measures. Constrain them"
# puts $xfh "# loosely rather than false-pathing, so they stay visible but cannot"
# puts $xfh "# dominate WNS."
# puts $xfh "set_input_delay  -clock sys_clk 0.100 \[remove_from_collection \[all_inputs\] \[get_ports clk\]\]"
# puts $xfh "set_output_delay -clock sys_clk 0.100 \[all_outputs\]"
close $xfh

add_files -fileset constrs_1 -norecurse $xdc_path

set_property top lumberjack_BenchTop [current_fileset]

# ---- Synthesis + implementation ---------------------------------------------
synth_design -mode out_of_context -top lumberjack_BenchTop -part $part \
    -generic CELL_INSTANCES=$cells \
    -generic USE_SUPERSCALAR=$superscal

opt_design
place_design
phys_opt_design
route_design

# ---- Reports -----------------------------------------------------------------
report_utilization -hierarchical -file $outdir/utilization.rpt
report_timing_summary -delay_type max -file $outdir/timing.rpt
report_timing -max_paths 20 -sort_by group -file $outdir/paths.rpt

# Vectorless power estimate. Without a SAIF this uses default toggle rates, so
# treat the absolute number with caution -- it is meaningful for comparing
# configurations against each other, not as a datasheet figure.
set_switching_activity -default_toggle_rate 25.0 -default_static_probability 0.5
set_operating_conditions -ambient_temp 25.0
report_power -file $outdir/power.rpt

# ---- Machine-readable summary ------------------------------------------------
# Count primitives directly: utilisation report row labels differ between
# 7-series and UltraScale+, PRIMITIVE_GROUP and PRIMITIVE_SUBGROUP do not.

# Logic LUTs vs distributed RAM/SRL. A LUT6 configured as memory reports
# PRIMITIVE_SUBGROUP of LUTRAM or SRL rather than LUT.
set all_luts [get_cells -hier -filter {PRIMITIVE_GROUP == LUT}]
set lutram_cells [get_cells -hier -filter {PRIMITIVE_SUBGROUP == LUTRAM || PRIMITIVE_SUBGROUP == SRL}]

set luts   [expr {[llength $all_luts] - [llength $lutram_cells]}]
set lutram [llength $lutram_cells]
set ffs    [llength [get_cells -hier -filter {PRIMITIVE_GROUP == FLOP_LATCH}]]
set brams  [llength [get_cells -hier -filter {PRIMITIVE_GROUP == BLOCKRAM}]]
set dsps   [llength [get_cells -hier -filter {PRIMITIVE_GROUP == ARITHMETIC}]]

# Timing
set paths [get_timing_paths -delay_type max -max_paths 1]
if {[llength $paths] > 0} {
    set wns [get_property SLACK $paths]
} else {
    set wns "null"
}

set fh [open $outdir/summary.yml w]
puts $fh "part: $part"
puts $fh "cells: $cells"
puts $fh "superscalar: $superscal"
puts $fh "target_period_ns: $period"
puts $fh "wns_ns: $wns"
if {$wns ne "null"} {
    puts $fh "fmax_mhz: [format %.2f [expr {1000.0 / ($period - $wns)}]]"
} else {
    puts $fh "fmax_mhz: null"
}
puts $fh "luts: $luts"
puts $fh "lutram: $lutram"
puts $fh "ffs: $ffs"
puts $fh "brams: $brams"
puts $fh "dsps: $dsps"
close $fh

puts "SUMMARY $part cells=$cells ss=$superscal wns=$wns fmax=[expr {$wns ne {null} ? 1000.0/($period-$wns) : 0}] luts=$luts lutram=$lutram ffs=$ffs brams=$brams dsp=$dsps power=$p_total"