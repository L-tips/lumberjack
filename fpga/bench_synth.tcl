# bench_synth.tcl
# vivado -mode batch -source bench_synth.tcl -tclargs <part> <period_ns> <outdir> <cells> <superscalar>

set part      [lindex $argv 0]
set period    [lindex $argv 1]
set outdir    [lindex $argv 2]
set cells     [lindex $argv 3]
set superscal [lindex $argv 4]

file mkdir $outdir
create_project -in_memory -part $part

set fp [open "../lumberjack.f" r]
set srcs [list]
while {[gets $fp line] >= 0} {
    if {[string trim $line] eq "" || [string match "#*" $line]} { continue }
    lappend srcs $line
}
close $fp
add_files -norecurse $srcs

set_property top BenchTop [current_fileset]
update_compile_order -fileset sources_1

# Timing-only constraint: no pins needed in OOC mode.
create_clock -period $period -name sys_clk [get_ports clk]

synth_design -mode out_of_context -top BenchTop -part $part \
    -generic CELL_INSTANCES=$cells \
    -generic USE_SUPERSCALAR=$superscal

opt_design
place_design
phys_opt_design
route_design

report_utilization -hierarchical -file $outdir/utilization.rpt
report_timing_summary -delay_type max -file $outdir/timing.rpt
report_timing -max_paths 20 -sort_by group -file $outdir/paths.rpt

# Machine-readable summary
set wns [get_property SLACK [get_timing_paths -delay_type max]]
set fh [open $outdir/summary.yml w]
puts $fh "part: $part"
puts $fh "cells: $cells"
puts $fh "superscalar: $superscal"
puts $fh "target_period_ns: $period"
puts $fh "wns_ns: $wns"
puts $fh "fmax_mhz: [expr {1000.0 / ($period - $wns)}]"
close $fh