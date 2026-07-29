for part in xc7a35tftg256-1 xczu3eg-sfvc784-2-e; do
  for cells in 1 2 4 6; do
    for ss in 0 1; do
      echo -e "$part\t$cells\t$ss"
    done
  done
done | parallel --colsep '\t' -j4 \
  'vivado -mode batch -nojournal -nolog -source bench_synth.tcl \
     -tclargs {1} 5.0 results/{1}_c{2}_ss{3} {2} {3} > logs/{1}_c{2}_ss{3}.log 2>&1'