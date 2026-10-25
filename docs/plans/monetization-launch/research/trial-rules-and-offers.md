# FTF: trial mechanisms, the post-trial paywall, Founder's Club pricing, and benchmarks

Research worker report for `monetization-pm`. **All pages accessed 2026-10-24** unless noted. Builds on `origin/plan/pricing:docs/plans/pricing/research/platform-and-benchmarks.md` (PR #347) (2026-10-15, "prior research"), cited as **[PR §n]** where it already answers a question.

Labels: **[interpretation]** = my reading, not Apple text. **[unverified]** = could not confirm on a primary page. **[benchmark]** = third-party aggregate data, correlational. "Not found" = searched for and not on the pages read.

**Guidelines version.** https://developer.apple.com/app-store/review/guidelines/ now reads "**Last Updated: October 16, 2026**", newer than the June 8, 2026 text in [PR §2]. The 2026-10-16 change list (https://developer.apple.com/news?id=92th7e5i) touches 3.1.1(a) ("clarified that links may be provided to a permitted destination") and adds 2.5.19 (hidden/dormant features) and 2.3.14 (creative assets). It does **not** touch 3.1.1, 3.1.2, 3.1.3, 2.1 or 5.1.1, or anything about trials or subscriptions.

---

## 1. Two trial mechanisms: are both allowed?

### Guideline text (verbatim, guidelines page, accessed 2026-10-24)

**3.1.1 In-App Purchase** (relevant bullets):
> If you want to unlock features or functionality within your app, (by way of example: subscriptions, in-game currencies, game levels, access to premium content, or unlocking a full version), you must use in-app purchase. Apps may not use their own mechanisms to unlock content or functionality, such as license keys, augmented reality markers, QR codes, cryptocurrencies and cryptocurrency wallets, etc.

> Any credits or in-game currencies purchased via in-app purchase may not expire, and you should make sure you have a restore mechanism for any restorable in-app purchases.

> Non-subscription apps may offer a free time-based trial period before presenting a full unlock option by setting up a Non-Consumable IAP item at Price Tier 0 that follows the naming convention: "XX-day Trial." Prior to the start of the trial, your app must clearly identify its duration, the content or services that will no longer be accessible when the trial ends, and any downstream charges the user would need to pay for full functionality. Learn more about managing content access and the duration of the trial period using Receipts and DeviceCheck.

**3.1.2 Subscriptions**, intro:
> Apps may offer auto-renewable in-app purchase subscriptions, regardless of category on the App Store. When incorporating auto-renewable subscriptions into your app, be sure to follow the guidelines below.

**3.1.2(a) Permissible uses** (full opening, plus the bullets that matter here):
> If you offer an auto-renewable subscription, you must provide ongoing value to the customer, and the subscription period must last at least seven days and be available across all of the user's devices. While the following list is not exhaustive, examples of appropriate subscriptions include: new game levels; episodic content; multiplayer support; apps that offer consistent, substantive updates; access to large collections of, or continually updated, media content; software as a service ("SAAS"); and cloud support. In addition:

> As with all apps, those offering subscriptions should allow a user to get what they've paid for without performing additional tasks, such as posting on social media, uploading contacts, checking in to the app a certain number of times, etc.

> If you are changing your existing app to a subscription-based business model, you should not take away the primary functionality existing users have already paid for. …

> **Auto-renewable subscription apps may offer a free trial period to customers by providing the relevant information set forth in App Store Connect.** Learn more about providing subscription offers.

> Apps that attempt to scam users will be removed from the App Store. This includes apps that attempt to trick users into purchasing a subscription under false pretenses or engage in bait-and-switch and scam practices; these will be removed from the App Store and you may be removed from the Apple Developer Program.

**3.1.2(b) Upgrades and Downgrades:**
> Users should have a seamless upgrade/downgrade experience and should not be able to inadvertently subscribe to multiple variations of the same thing. Review best practices on managing your subscription upgrade and downgrade options.

**3.1.2(c) Subscription Information:**
> Before asking a customer to subscribe, you should clearly describe what the user will get for the price. How many issues per month? How much cloud storage? What kind of access to your service? Ensure you clearly communicate the requirements described in Schedule 2 of the Apple Developer Program License Agreement.

(Schedule 2 §3.8(b) disclosure list: see [PR §5].)

**2.2 Beta Testing** (the only other "trial" sentence in the guidelines):
> Demos, betas, and trial versions of your app don't belong on the App Store – use TestFlight instead.

**Free-trial disclosure.** From Apple's subscriptions page, https://developer.apple.com/app-store/subscriptions/:
> In the purchase flow for a free trial, clearly indicate how long the free trial lasts and the price billed once the free trial is over.

> **Free trial.** A subscriber can access your subscription for free for a specific duration … Their subscription begins immediately, but they won't be billed until the offer duration ends.

Required sign-up-screen elements (same page): "Subscription name and duration, and the content or services provided during the subscription period"; "Full renewal price, shown clearly and prominently, and localized in available currencies"; "A way for current subscribers to sign in or restore purchases"; and "your app and App Store metadata must include links to your Terms of Use and Privacy Policy."

### Mechanism (1): StoreKit intro offer, 1-month free trial, auto-converts

**Allowed. This is the path the guidelines sanction by name** (the 3.1.2(a) bullet above).
- "1 Month" is a valid free-trial duration for monthly and annual products. The full list is "3 Days. 1 or 2 Weeks. 1, 2, 3, or 6 Months. 1 Year." Source: App Store Connect Help, intro offers, https://developer.apple.com/help/app-store-connect/manage-subscriptions/set-up-introductory-offers-for-auto-renewable-subscriptions
- There is no "30 days" option [PR §4]. **[interpretation]** Marketing copy should say "1-month free trial" or "free for a month." A calendar month isn't always 30 days, and 2.3.1(a) bars "promoting a false price".
- **Paywall-design enforcement since mid-January 2026 (secondary source).** Apple rejects paywalls with a free-trial **toggle** under 3.1.2. RevenueCat (published 2026-02-09, updated 2026-04-23, https://www.revenuecat.com/blog/growth/rip-toggle-paywall) quotes the rejection: "The purchase screen includes a toggle to add or remove a free trial from the subscription purchase … This design is confusing and may prevent users from understanding that they are committing to an auto-renewing subscription." Compliant alternatives it names: a timeline paywall (today / reminder / charge date) and a multi-plan selector with the trial plan badged.

### Mechanism (2): app-managed 30-day window from first sign-in, then a hard paywall

**No guideline sentence explicitly forbids it, and none explicitly permits it for subscription apps. App Review has rejected it, citing the 3.1.2(a) free-trial bullet.**

- **Tier-0 bullet:** it is addressed to "**Non-subscription apps**", so by its text it does not cover FTF. Nothing in 3.1.1 or 3.1.2 says "subscription apps may *only* offer trials through App Store Connect." The 3.1.2(a) wording is permissive ("may offer"). **[interpretation]**
- **2.2 risk:** a reviewer could read an app that stops working at day 30 as a "trial version." **[interpretation]** 2.2 targets separate demo/trial binaries, and Apple's own trial mechanisms show time-limited access inside a full app is acceptable. Still, it is a hook for a rejection.
- **Rejection evidence.** Apple Developer Forums thread 129010, https://developer.apple.com/forums/thread/129010 (community posts; no Apple staff reply):
  - Feb 2020: an app with "Free until <calculated date 30 days after first launch>" (first-launch date stored in Keychain) was rejected: "We noticed that your app offers a free trial without implementing the offer in App Store Connect."
  - Feb 2020, a second developer, fuller text: "We noticed that your app offers a free trial without implementing the offer in App Store Connect. Offering free trials through App Store Connect ensures that when the free trial period is over, the user will automatically be billed (unless the user has cancelled the subscription). … To resolve this issue, please use App Store Connect to implement free trials."
  - Mar 2020: a third developer reported the same rejection and said it hit an onboarding screen that earlier approved versions had shipped.
- **Thread 132546** (May 2020), https://developer.apple.com/forums/thread/132546: a developer's own 30-day trial (no login, no card) was rejected. They say an App Review representative told them by phone that users "had to commit to the free trial through in-app purchases," and cited the 3.1.2(a) free-trial bullet. This is a secondhand account, and the outcome isn't stated.
- **Counter-evidence (secondhand, May 2025, same thread 129010):** "I talked to Apple and they told me this is fine as long as it's clear to the user that the free trial has started already and that the app is not free." No outcome was posted.
- **Net:** the only documented outcomes are 2020 rejections. One unverified 2025 report says it is acceptable with clear disclosure. **I found no 2024–2026 report of an approval or rejection of this exact pattern.** Treat it as review risk, not a rule.

### The Tier-0 "XX-day Trial" non-consumable inside subscription apps

- **Mixed, old evidence.** Thread 129010, May 2020: "We were able to get a version of our application approved that used a non-consumable Tier 0 IAP for the free trial. Once the trial period is done, the user has the option to purchase the yearly subscription." A later bug-fix release with no trial changes "was rejected with the reason that we are potentially trying to mislead the user."
- **RevenueCat staff (community, 2025-02-06):** suggested granting an entitlement from the backend, or "selling" a "$0 non-renewing in-app purchase (that lasts 14 days)". A member then said they don't believe a $0 non-renewing subscription can be created. Staff concluded: "I would generally recommend using a typical trial or the $0 purchase workaround." https://community.revenuecat.com/general-questions-7/start-of-free-trial-period-without-automatic-subscription-5821
- **[interpretation]** The literal text scopes Tier-0 trials to non-subscription apps, so it is not a safe harbor for FTF. Its disclosure standard is still the best template for an app-managed trial: duration, what is lost, downstream charges, all shown "prior to the start of the trial".

### Can (2) be combined with a StoreKit intro offer?

- **No rule against it was found.** Eligibility is tracked by StoreKit per subscription group, not by app-managed state. A user who never bought in the group is a new subscriber. "New subscribers are always eligible." "Existing subscribers are not eligible for an introductory offer for any product within the same subscription group. For example, customers are not eligible if they are upgrading, downgrading, or crossgrading their subscription from another product, regardless of whether they consumed an introductory offer in the past." Source: StoreKit "Implementing introductory offers in your app", https://developer.apple.com/documentation/storekit/implementing-introductory-offers-in-your-app (original API doc).
- **Consequence:** if the product shown at day 30 carries a 1-month free-trial intro offer, the user gets a second free month.
  - Intro offers are configured per product per storefront ("one current and one future introductory offer per storefront").
  - I found no Apple text letting the app withhold an intro offer from an eligible buyer. Assume StoreKit applies it **[unverified]**.
  - Options:
    - "No further trial": configure **no** intro offer on the products offered after the window.
    - "Short one": configure "3 Days" or "1 or 2 Weeks".
    - Use the intro slot for a **discount** instead: pay-up-front or pay-as-you-go, up to 1 year (§3b).

---

## 2. The hard paywall after expiry

### What must stay reachable

- **Account deletion. 5.1.1(v):** "If your app supports account creation, you must also offer account deletion within the app." Apple's account-deletion page, https://developer.apple.com/support/offering-account-deletion-in-your-app/, adds:
  - "Apps submitted to the App Store that support account creation must also let people initiate deletion of their account within the app."
  - "**Make the account deletion option easy to find in your app.** Typically, it's included in the app's account settings."
  - "only offering to temporarily deactivate or disable an account is insufficient."
  - "If a person has an auto-renewable subscription, notify them that billing will continue through Apple and ask them to cancel their subscription before continuing."
  - "you can offer to schedule account deletion for a later date, aligned with the subscription's expiration, as long as there's also an option to delete the account immediately."
  - **[interpretation]** The post-trial paywall must not trap users. Account settings, or at least Delete Account, must be reachable from the locked state.
- **Data export:** **not found** in the App Review Guidelines. 5.1.1(i) only requires the privacy policy to "describe how a user can revoke consent and/or request deletion of the user's data."
- **Restore Purchases:**
  - 3.1.1 (quoted above): "you should make sure you have a restore mechanism for any restorable in-app purchases."
  - The subscriptions page lists, as a required sign-up-screen element, "A way for current subscribers to sign in or restore purchases."
  - StoreKit (original API), https://developer.apple.com/documentation/storekit/restoring-purchased-products: "Include some mechanism in your app, such as a Restore Purchases button, to let them restore their purchases." and "Don't automatically restore purchases, especially when your app launches."
  - The HIG in-app-purchase page was **not retrieved** (404 on the JSON endpoint).
- **Privacy policy and terms links:**
  - 5.1.1(i): "All apps must include a link to their privacy policy in the App Store Connect metadata field and within the app in an easily accessible manner."
  - Subscriptions page: "your app and App Store metadata must include links to your Terms of Use and Privacy Policy."
  - DPLA Sched. 2 §3.8(b) requires in-app Privacy Policy and Terms of Use links [PR §5].

### Is "not functional after trial" a problem?

- **No guideline bars a hard paywall.** Hard paywalls are a mainstream model; RevenueCat's SOSA 2026 benchmarks them separately (§4).
- In thread 132546, App Review required a StoreKit trial paywall *before* any use, which implies a day-0 hard paywall is accepted.
- Text that a reviewer could invoke:
  - **4.2:** "If your App doesn't provide some sort of lasting entertainment value or adequate utility, it may not be accepted."
  - **2.2:** "trial versions … don't belong on the App Store."
  - **3.1.2(a):** "should not take away the primary functionality existing users have already paid for". This doesn't apply: FTF has no paying App Store users.
- **[interpretation]** The risk is low if the locked state is clearly a subscription paywall with working IAP, restore and account settings, rather than a dead end.

### App Review access

- **2.1(a):** "include demo account info (and turn on your back-end service!) if your app includes a login. If you are unable to provide a demo account due to legal or security obligations, you may include a built-in demo mode in lieu of a demo account with prior approval by Apple. Ensure the demo mode exhibits your app's full features and functionality."
- **2.1(b):** "If you offer in-app purchases in your app, make sure they are complete, up-to-date, visible to the reviewer and functional. If any configured in-app purchase items cannot be found or reviewed in your app, explain the reason in your review notes."
- **2.3.1(a):** "All new features, functionality, and product changes must be described with specificity in the Notes for Review section of App Store Connect (generic descriptions will be rejected) and accessible for review."
- **New 2.5.19 (2026-10-16):** "Don't include any hidden, dormant, or undocumented features in your app; your app's functionality should be clear to end users and App Review." **[interpretation]** A day-30 lock, a Founder's Club cutoff and server-flagged trial modes are states the reviewer won't reach on their own. Document each in Review Notes.
- **Sandbox:** Apple's archived In-App Purchase FAQ (TN2413) says App Review reviews apps in the sandbox, so reviewer purchases are sandbox purchases, not real charges. https://developer.apple.com/library/archive/technotes/tn2413/_index.html (archived doc; not re-fetched).
- **[interpretation] Practical setup:**
  - Demo account A: a fresh in-window account with a demo league.
  - Demo account B: an account whose 30-day window has already expired, so the paywall shows immediately.
  - Keep "Subscribe" reachable from Settings during the window, so the IAPs are "visible to the reviewer" under 2.1(b) whichever account is used.

---

## 3. Founder's Club: "founder price locked for as long as you stay subscribed"

### (a) Separate "Founder" SKU in the same subscription group

- **You cannot stop new sales while keeping founders renewing**, per Apple's docs. App Store Connect Help, https://developer.apple.com/help/app-store-connect/manage-subscriptions/set-availability-for-an-auto-renewable-subscription/: "Before discontinuing an auto-renewable subscription, remove it from sale, within App Store Connect, **to stop additional sign-ups and renewals**."
  - The only "existing keep / new can't" switch on that page is for the non-US 12-month-commitment billing option ("Existing customers won't renew at the end of their 12 month commitment, and new customers won't be able to subscribe").
  - A community post claims a "No longer available for new subscribers" setting exists. **Not found in Apple docs [unverified].** https://developer.apple.com/forums/thread/829942
- **If you leave it on sale and only hide it in your paywall, everyone in the group can find it.**
  - Apple App Store Commerce Engineer (2022): "Once the user subscribes, they can access all subscriptions from within the subscription group that the subscription belongs to, and upgrade/downgrade/cancel at any time." https://developer.apple.com/forums/thread/716772
  - Apple Staff (Jun 2026): "It is expected that all subscriptions show in the subscriptions section on the App Store." https://developer.apple.com/forums/thread/829942
  - So any regular Pro subscriber could crossgrade to the $24.99 founder SKU from Settings, indefinitely.
- **Levels and crossgrade** (subscriptions page):
  - "If both subscriptions are pay-up-front subscriptions and the same duration, the new subscription begins immediately. If the durations are different, the new subscription goes into effect at the next renewal date."
  - Upgrades are immediate with a prorated refund; downgrades wait for the next renewal. See also [PR §3].
- **Own intro offer:** yes. Intro offers are set per product. But eligibility is per group: "each person is only eligible to redeem one introductory offer per subscription group. … if a customer uses a free trial and then upgrades to a subscription product in the same group that also has a free trial, they aren't eligible for the second offer." **Confirmed:** a user who trialled monthly can't trial the founder annual in the same group. Existing subscribers switching products are never intro-eligible (StoreKit doc, §1).
- **A separate group avoids Manage Subscriptions exposure** ("Subscriptions group is not visible on the Manage subscriptions page to the user until they subscribe", thread 716772). It also gets its own intro eligibility. The cost: users can hold two Pro subscriptions at once, which cuts against 3.1.2(b) ("should not be able to inadvertently subscribe to multiple variations of the same thing"). **[interpretation]** Not recommended.

### (b) Introductory discount ("pay up front" / "pay as you go")

- **Confirmed: it conflicts with a free-trial intro.**
  - Each product has one intro offer per storefront: "You can have one current and one future introductory offer per storefront."
  - Each customer gets one intro per group.
  - So a product can carry either the 1-month free trial or a founder discount as its intro, not both.
- **Also time-boxed.** For annual products, pay-as-you-go maxes at "1 Year" and pay-up-front at "1, 2, 3, or 6 Months. 1 Year." For monthly products, pay-as-you-go runs "1 to 12 Months". After that, the standard price applies. **Cannot give a permanent price.**

### (c) Offer codes

Source: App Store Connect Help, https://developer.apple.com/help/app-store-connect/manage-subscriptions/set-up-subscription-offer-codes

- **Eligibility:** "New subscribers: Customers who have never subscribed to any subscription product within the group." "Existing subscribers: … currently subscribed … This includes subscribers in billing retry or a grace period, as long as auto-renew remains enabled." "Expired subscribers: … previously subscribed … auto-renew is turned off and subscription period has ended." You can select one or more of these.
- **Existing subscribers** (subscriptions page): "Existing subscribers can only redeem codes that are an upgrade from or at the same level as their current subscription."
- **Types and duration:** pay as you go, pay up front or free; "Choose the appropriate duration". **No maximum offer duration is stated on the page (not found).** The six-month limit is on code validity: "One-time use codes can be valid for a maximum of six months."
- **Limits:**
  - "maximum of 1 million redemptions per app, per quarter"
  - "up to 10 active offers per subscription SKU at a time"
  - "Customers are limited to redeeming one code per offer."
- **Code types:**
  - One-time-use: batches of "a minimum of 500 and a maximum of 25,000".
  - Custom: "up to 64 characters", "a limit of up to 25,000 at a time"; "An expiration date isn't required for custom codes."
- **After the offer:** renews "to the standard price upon conclusion of the offer period". You can tick no-auto-renew for free offers only.
- **Stacking with the intro offer:** "Eligible customers will redeem your app's introductory offer first, then automatically renew to the offer they redeemed with the code." So a code can give a 1-month free trial followed by a discounted period, then the standard price.
- **Distribution:**
  - "You're responsible for distributing offer codes to your customers."
  - Redemption URL, App Store "Redeem Gift Card or Code", or in-app via the StoreKit redemption sheet.
  - "In order for offer codes to be redeemed, your app must be available on the App Store."
- **A permanent price: no.** The offer is time-limited, then the standard price applies.

### (d) Promotional offers

- **Eligibility is still existing or lapsed subscribers only.**
  - App Store Connect Help, https://developer.apple.com/help/app-store-connect/manage-subscriptions/set-up-promotional-offers-for-auto-renewable-subscriptions: "a discounted price for a specific duration for existing and previously subscribed customers". New customers aren't mentioned.
  - StoreKit doc, https://developer.apple.com/documentation/storekit/implementing-promotional-offers-in-your-app: "The App Store deems all customers with an existing or expired subscription in the app eligible to redeem a promotional offer." and "If your goal is to attract new users, you can use introductory offers".
  - "Customers can accept the offer even if they've already accepted an introductory offer."
- **Duration:** the maximum is **not found** on the pages read. Types are free, pay as you go or pay up front. "Once the offer period concludes, a promotional offer auto-renews at the standard price."
- **Server signature:** "A signature is a unique string that your server generates using specified parameters and your private key." "The signature is time sensitive, unique per offer, and redeemable only once." The current StoreKit 2 JWS signing format was not checked **[not retrieved]**.
- **Limits and timing:**
  - "up to 10 active offers per subscription"
  - "A user can redeem and have active only one promotional offer at a time."
  - "When a customer redeems a promotional offer, the offer period starts at the next billing event." This resolves [PR §4]'s open timing question.
- **Not a permanent price.** Re-issuing an offer every period would need the user to tap through Apple's sheet each time. **[interpretation]** Too fragile to back a lifetime promise.

### (e) Price preservation ("keep the current price for existing subscribers")

Source: App Store Connect Help, https://developer.apple.com/help/app-store-connect/manage-subscriptions/manage-pricing-for-auto-renewable-subscriptions

- **The option:** "A: Keep the current price for existing subscribers. Anyone who subscribed before the start date of this price change won't be affected. Subscribers whose subscription expires can resubscribe at the preserved price within 60 days of expiration."
- **No cap on cohort size** (subscriptions page): "You can keep an unlimited number of active subscribers at their existing price while increasing the price for new subscribers."
- **Free trials count:** "Their subscription begins immediately, but they won't be billed until the offer duration ends" (subscriptions page). **[interpretation]** A user in a StoreKit free trial when the increase takes effect has "subscribed before the start date" and keeps the founder price.
- **Reversible by FTF later:** "Un-preserve prices for subscribers … Any changes you make can't be reversed." Consent rules then apply [PR §6]. So "locked forever" is FTF's promise, not Apple's guarantee. DPLA Sched. 2 §3.8(c): "must fulfill the offer during the entire subscription period, as marketed" [PR §5].
- **Other limits:**
  - "you can schedule one future price change at a time, per country or region, per billing plan type."
  - Price decreases always pass through to everyone.
  - **[unverified]** Whether a founder who crossgrades (for example monthly to annual) keeps a preserved price on the *other* product. Assume not, since preservation attaches to the product they were on.

### Recommendation: (e) price preservation

Launch Pro at the founder price (e.g. $24.99/yr). On the club-close date, schedule a price increase for new subscribers with **"Keep the current price for existing subscribers."**

Why:
1. It is the only Apple-native mechanism that is not time-boxed. (b), (c) and (d) all renew to the standard price.
2. It uses one SKU in one group. Nothing extra shows in Manage Subscriptions, which avoids the crossgrade leak in (a).
3. No server signing, no code distribution, no cap on how many founders.
4. It composes with the 1-month StoreKit trial: anyone who *starts* a trial before close is grandfathered automatically.

Caveats:
- With mechanism (2), the user isn't "subscribed" until they pay. Founder status then needs a real purchase before the close date. A rolling 30-day window from first sign-in won't line up with a fixed close date (users who join in the last 30 days before close run past it).
- Spell out the lapse rule (60 days) and the plan-switch rule in the Terms and the paywall copy.
- Use offer codes for creators and partners, and promotional or win-back offers for retention. They are additive, not the lock.

---

## 4. Benchmarks (all [benchmark] unless marked; correlational)

**Opt-in (no payment up front) vs opt-out (StoreKit, payment method on file)**
- **No primary mobile-app dataset that splits opt-in from opt-out was found.**
- Secondary source: Eightx (published 2026-05-30), https://eightx.co/blog/average-ecommerce-subscription-trial-to-paid-conversion-by-vertical-2026, attributes to Adapty's *State of In-App Subscriptions 2026*: "Opt-out free trials (credit card required) convert at 31.4%; opt-in free trials (no card) convert at 8.9%".
  - **Not found on Adapty's own report page.** Eightx also misstates Adapty's sample (it cites 115,000+ apps, which is RevenueCat's figure). **Low confidence.**
- SaaS data (FirstPageSage, 86 SaaS companies, Q1 2022 to Q3 2025, via the Adapty blog updated 2026-03-01, https://adapty.io/blog/trial-conversion-rates-for-in-app-subscriptions/):

  | Model | Visitor-to-trial | Trial-to-paid | Visitor-to-paid [computed] |
  |---|---|---|---|
  | Opt-in | 8.5% | 18.2% | ≈1.5% |
  | Opt-out | 2.5% | 48.8% | ≈1.2% |
  | Freemium | 13.3% | 2.6% | — |

  The page says opt-out converts "roughly 2.5 to 3 times" better at trial-to-paid, and opt-in brings "3 to 4 times more signups."
- Reverse trial: RevenueCat SOSA 2026 (https://www.revenuecat.com/state-of-subscription-apps) defines it as premium access "after they dismiss the offer — no credit card required". Its only figure is a practitioner anecdote: "We've seen this increase freemium conversions from 0.4% to 4.5%" (Steve P. Young). That is not RevenueCat data.
- Mobile overall: Adapty 2026 global install-to-trial **10.9%**, trial-to-paid **25.6%**, Entertainment **19.1%** trial-to-paid. Trial subscribers retain "1.4-1.7x better than direct buyers". https://adapty.io/state-of-in-app-subscriptions/

**Hard paywall at day 0 vs a delayed paywall**
- **No rigorous public A/B of day-0 vs delayed paywalls was found.** Results were vendor opinion or small-n anecdotes.
- SOSA 2026:
  - Day-35 download-to-paid: hard paywall median **10.7%** vs freemium **2.1%**. Year-one retention is "nearly identical."
  - "Nearly all trial starts happen on Day 0 across categories" (78–90% by category).
  - Day 0 accounts for **50.6%** of paid conversions. The report also says elsewhere "1/3 of all conversions happen on day zero", which conflicts.
- Adapty 2026: "90% of trial starts happen on Day 0"; "Hard paywalls generate 21% higher LTV per subscriber than soft paywalls."
- **[interpretation]** An app-managed window gives up the day-0 decision moment where most trial starts happen. The paywall moves to day 30, when intent may have cooled or peaked.

**Trial length: 30-day vs 7-day.** Refreshed; nothing newer than RevenueCat 2026-09-28 was found.
- SOSA 2026 median trial-to-paid: ≤4 days 25.5%, 5–9 days 37.4%, 10–16 days 35.4%, **17–32 days 42.5%**. Share of trial cancellations that happen on Day 0: 30-day 31.1%, 14-day 35.7%, 7-day 39.8%.
- RevenueCat (2026-09-28), 17–32-day trials: **43.7%** on monthly plans, **44.6%** on annual plans; annual first renewal 47.5% [PR §8].
- Adapty (updated 2026-03-01): 1–4 days 30%, 5–9 days 45%, 10–16 days 44%, **17–32 days 45.7%**. Cancellation before trial end: 51% for 30-day trials vs 26% for 3-day.

**Social, multiplayer and network-dependent apps**
- **No rigorous dataset was found.**
- SOSA 2026: in Social & Lifestyle, the no-trial strategy holds **43.6%**, the highest of any category and the only one where no-trial beats mixed-trial. Media & Entertainment's trial-to-paid spread is the widest (**11.5%–69.5%**). Late conversion (after the first days) is 24–25% in both categories.
- Vendor blogs (opinion only) argue for freemium where free users feed the network, e.g. https://www.setgreet.com/blog/free-trial-vs-hard-paywall and https://vmobify.com/blog/freemium-vs-free-trial.
- **[interpretation]** FTF's trade value depends on leaguemates being present. A hard lock at day 30 cuts free leaguemates out of the network that paying users need. Consider whether a locked user still counts as a trade counterparty server-side, even though their app is locked.

---

## 5. Web and extension

- **One line:** yes. On the US storefront the web app or extension can sell the same subscription through Stripe, and the iOS app can link to it with no entitlement and **0% Apple commission today**. The litigation risk and fee stack are in [PR §2, §7].
- **Current text** (guidelines, Last Updated 2026-10-16):
  - **3.1.1(a):** "Developers may apply for entitlements to provide a link in their app to a **permitted destination** in order to purchase digital content or services. These entitlements are not required for developers to include buttons, external links, or other calls to action in their United States storefront apps." It continues: "In all other storefronts, except for the United States storefront, where this prohibition does not apply, apps and their metadata may not include buttons, external links, or other calls to action that direct customers to purchasing mechanisms other than in-app purchase." The wording changed on 2026-10-16 from "a website the developer owns or maintains responsibility for" to "a permitted destination".
  - **3.1.3:** "Apps in this section cannot, within the app, encourage users to use a purchasing method other than in-app purchase, except for apps on the United States storefront and as set forth in 3.1.1(a) and 3.1.3(a)."
  - **3.1.3(b):** web-acquired access is allowed in-app "provided those items are also available as in-app purchases within the app."
- **"Or subscribe on the web" on the iOS paywall: allowed on the US storefront** under the text above. The Ninth Circuit lets Apple require that the link be no more prominent than the IAP option [PR §2]. Keep the IAP option equal and the 3.1.1 IAP requirement satisfied.
- **New 2.3.14:** App Store creative assets must not include "specific or discounted pricing information". Founder pricing can't go in creative assets; it can go in-app and on the web.

---

## Implications for FTF

1. **The StoreKit 1-month free trial is the review-safe path.** 3.1.2(a) names it. Configure and market it as "1 month," not "30 days."
2. **The app-managed 30-day window is not forbidden by any guideline text, but App Review has rejected it.** The rejection read "free trial without implementing the offer in App Store Connect" (2020, citing 3.1.2(a)). The only counter-evidence is one secondhand 2025 report. With the binary due 2026-11-10, choosing it means accepting a real rejection risk with little time to resubmit.
3. **If the app-managed window ships:** disclose duration, what locks and the price before the window starts (borrow the 3.1.1 Tier-0 wording), and never call the app "free". Describe it in Review Notes (2.3.1(a), 2.5.19). Have the StoreKit-trial configuration ready as the fallback.
4. **Don't stack trials by accident.** An app-managed window user is still StoreKit-intro-eligible. A 1-month intro on the day-30 product gives about 60 days free. Use no intro, or a short one, on that product.
5. **Founder's Club: use price preservation.** Launch at the founder price. At club close, raise the price for new subscribers with "Keep the current price for existing subscribers". The cohort is unlimited, and StoreKit trial starters before close are grandfathered.
6. **Don't build a separate founder SKU in the Pro group.** "Remove from sale" stops renewals. Leaving it on sale exposes it in Manage Subscriptions to every subscriber, who can crossgrade to it.
7. **Intro discounts, offer codes and promotional offers all expire to the standard price.** Use codes for creators and partners and promotional or win-back offers for retention, never as the "lock."
8. **"Locked as long as you stay subscribed" is FTF's contract, not Apple's.** Apple lets you un-preserve later. Put the 60-day lapse rule and the plan-switch caveat in the Terms and paywall copy (DPLA §3.8(c), 5.6).
9. **The locked state must keep reachable:** Restore Purchases, Terms and Privacy links, account settings with in-app account deletion (including the Apple-billing warning), and sign-out. A data-export path isn't required by the guidelines.
10. **Paywall design:** no free-trial toggle (rejections since January 2026). Make the billed amount the most prominent price, and state trial length and post-trial price. Give reviewers two demo accounts (in-window and expired) and keep Subscribe reachable from Settings during the window (2.1(b)).
11. **Benchmarks:** opt-out trials convert about 2.5–3.5× better at trial-to-paid. Opt-in trials draw about 3–4× more starts, roughly a wash end-to-end in SaaS data, and there is no reliable mobile opt-in data. 17–32-day trials have the best medians (42.5–45.7%). About 90% of trial starts and about half of conversions happen on Day 0, which favors putting the decision up front.
12. **Web:** "or subscribe on the web" is allowed on the US paywall today at 0% Apple commission, but keep the IAP option equal in prominence. Keep founder pricing out of App Store creative assets (2.3.14).
