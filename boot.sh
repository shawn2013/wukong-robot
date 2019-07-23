#!/bin/bash
#cur_path=$(cd $(dirname $0); pwd)
wukong_dir=/mnt/card/wukong
cd $wukong_dir
nohup sudo python3 wukong.py >/dev/null &