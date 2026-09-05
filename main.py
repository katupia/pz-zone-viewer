#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry point: python main.py"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pzzoneviewer.app import main

if __name__ == "__main__":
    main()
