// The ONE support address in the mobile app (#354 BL10-R7, BL-2).
//
// Every mobile use imports this constant, so the address is written as a
// literal exactly once in mobile/src, with an ordinary @ (U+0040), never the
// full-width U+FF20 look-alike. Web and the App Store listing hold the other
// two copies of the same value. Pinned by tests/check-feedback-public.js pin 3.
export const SUPPORT_EMAIL = 'fleecedapp@gmail.com';
