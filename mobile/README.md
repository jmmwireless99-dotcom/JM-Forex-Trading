# JM Forex — Android app

Expo React Native desk for **https://jmtechsolution.cloud/fx/**

Controls the same backend as the web desk: status, Auto transfer, strategy apply, start/stop, trades.

## Quickest way on Android (no build)

1. Open Chrome on your phone  
2. Go to **https://jmtechsolution.cloud/fx/**  
3. Menu → **Install app** / **Add to Home screen**  

That installs the PWA (same desk, app icon).

## Run with Expo Go (dev)

```bash
cd mobile
npm install
npx expo start
```

Scan the QR code with **Expo Go** (Android).  
Default API: `https://jmtechsolution.cloud/fx/api`

## Build an APK (installable file)

Needs an Expo account ([expo.dev](https://expo.dev)):

```bash
cd mobile
npm install
npx eas-cli login
npx eas build -p android --profile preview
```

Download the APK from the Expo build page and install on your phone  
(Settings → allow install from unknown sources if needed).

Package id: `cloud.jmtechsolution.forex`

## Features

- Live XAUUSD mid + account equity / daily P&L  
- **Auto transfer** (session-recommended strategy)  
- Select + **Apply strategy**  
- Start / Stop engine  
- Recent trade log  
- Custom API URL (for local VPS testing)

## Notes

- Phone app **controls** the desk — it does not run MetaTrader EA.  
- MT4/MT5 still needs a Windows terminal for live bridge execution.  
- Paper mode works fully from the phone against the VPS API.
