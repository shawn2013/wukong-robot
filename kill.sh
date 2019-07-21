#!/bin/bash
ps aux | grep "wukong.py" | grep -v 'color' | awk '{print $2}' | xargs kill -9
pkill -9 play
