#!/bin/bash
pip install -r requirements.txt
apt-get update -qq && apt-get install -y fpocket 2>/dev/null || true
