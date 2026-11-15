#!/bin/sh
# Copy the current local data into seed/, the snapshot shipped with the app.
set -e
rm -rf seed && mkdir -p seed/cache
cp data/finn.db seed/finn.db
cp data/cache/EQUITY_L.csv seed/cache/
cp -r data/cache/screener seed/cache/screener
[ -d data/cache/guidance ] && cp -r data/cache/guidance seed/cache/guidance
du -sh seed
