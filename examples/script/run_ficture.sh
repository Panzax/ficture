#!/bin/bash

# Activate the virtual environment
# source /home/eecs/martinalvarezkuglen/.cache/pypoetry/virtualenvs/pixelvi-eO-HYK6l-py3.11/bin/activate
conda activate ficture

# Make pixel level figures
data_dir="/data/yosef2/martinak/XeniumIPF225721"
ficture run_together \
    --in-tsv "${data_dir}/filtered.matrix.tsv.gz" \
    --in-minmax "${data_dir}/coordinate_minmax.tsv" \
    --in-feature "${data_dir}/features.tsv.gz" \
    --out-dir "${data_dir}/ficture_output2" \
    --train-width 12 \
    --n-factor 12,18 \
    --n-jobs 24 \
    --plot-each-factor \
    --all
