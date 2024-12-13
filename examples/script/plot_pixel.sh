#!/bin/bash

# Activate the virtual environment
# source /home/eecs/martinalvarezkuglen/.cache/pypoetry/virtualenvs/pixelvi-eO-HYK6l-py3.11/bin/activate
conda activate ficture

# Make pixel level figures
data_dir="/data/yosef2/martinak/XeniumIPF225721"
n_factor=12
pixel_resolution=0.5
output_id="nF${n_factor}.d_12"
output_path="${data_dir}/ficture_output/analysis/${output_id}"
figure_path="${output_path}/figure2"
prefix="${output_id}.decode.prj_12.r_4_5"
cmap="${output_path}/figure/${output_id}.rgb.tsv"
input="${output_path}/${prefix}.pixel.sorted.tsv.gz"
output="${figure_path}/${prefix}.pixel.png"
ficture plot_pixel_full --input ${input} --color_table ${cmap} --output ${output} --plot_um_per_pixel ${pixel_resolution} --full
