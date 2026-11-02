# GPS background probe (lab)

A throwaway page that answers one question for tasks 006 (Spotify songs) and 007 (walking
tours): does Chrome on Android keep delivering `watchPosition` fixes when the tour page is
hidden behind another app or the screen is locked, and does a playing audio element change that?

It uses the same `watchPosition` options and 5 s retry as `site/player/app.js`. It logs every
fix (accuracy, speed, fix age, gap since the previous fix), every GPS error, visibility changes,
`freeze`/`resume`/`pagehide`, audio-loop state, wake-lock changes, timer stalls and battery level
at each phase change. The log is stored in localStorage. The screen never shows coordinates,
and the shared log gives distances from the first fix unless you tick "Include raw coordinates".

The page isn't linked from the site index. It needs HTTPS for geolocation, so open it at
`<pages-url>/lab/gps-probe/` or through a tunnel.

## Test plan (Android Chrome, as a passenger or on a walk)

Close the tour tab first.

1. **Screen on**: Start GPS, tap *1 Screen on*, and keep the page in front for 2 minutes.
2. **Spotify**: tap *2 Spotify*, play a song in Spotify for 3 minutes, come back, tap *Mark*.
3. **Locked**: tap *3 Locked*, lock the screen with the page in front for 3 minutes, unlock,
   tap *Mark*.
4. **With the audio loop**: *4a Spotify + loop* (repeats step 2 with the quiet loop started),
   then *4b Locked + loop* (repeats step 3).
5. Tap *Done*, then *Share log*, and send the text back.

Read the summary row by row. The key columns are *hidFix* (fixes delivered while hidden) and
*maxGapHid* (the longest wait between fixes that overlapped hidden time).
