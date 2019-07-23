#!/bin/bash
ps aux | grep "wukong.py" | grep -v 'color' | awk '{print $2}' | xargs sudo kill -9
sudo pkill -9 play