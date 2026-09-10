## 📈 F&O Stocks List (Market Cap Filtered)

`symbols/` folder में NSE F&O eligible stocks की list है, जिसे Market Cap
के हिसाब से filter किया जा सकता है।

### List Generate करना
\`\`\`bash
cd symbols
python generate_fo_list.py --min-cap 45000
\`\`\`

### Zone Scanner के साथ इस्तेमाल
\`\`\`bash
python zone_scanner.py --symbols symbols/nifty_fo_45000cr.txt --intervals "15m,1h,1d"
\`\`\`

> ⚠️ NSE की F&O stocks list हर quarter बदलती है। `all_nse_fo_stocks.txt`
> को समय-समय पर [NSE Official Website](https://www.nseindia.com/market-data/equity-derivatives-watch)
> से update करते रहें।
