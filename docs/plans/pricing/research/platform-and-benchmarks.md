# FTF pricing memo: App Store / StoreKit rules, fees, and subscription benchmarks

Research worker report for `monetization-pm`. As of **2026-10-15**. Public sources only; every web page below was accessed on 2026-10-15 unless a different date is given. "Published" dates come from the page itself. Where the text says **[interpretation]** or **[unverified]**, the conclusion is mine or could not be confirmed against a primary source.

Context assumed: US-only, solo developer, pre-revenue, RevenueCat (`react-native-purchases` 10.8.1), Pro monthly $4.99 (14-day trial) and annual $34.99 (30-day trial) in one subscription group. Planned: Season Pass 2026 (~$19.99), Founder lifetime ($99–119, cap 100), three tip consumables, maybe a spring Rookie Pass (~$9.99), a give-get referral, and a possible Stripe Founder pre-order during TestFlight.

---

## 1. Apple commission today

**Standard rates (unchanged for US IAP in 2025–2026).**
- Standard commission is **30%**. For auto-renewable subscriptions, Apple takes **15%** on renewals once a customer has more than one year of paid service within a subscription group. Source: Apple Developer Program License Agreement (DPLA), Schedule 2 §3.4(a). Schedules 2 and 3 were last updated **2026-10-13**. https://developer.apple.com/support/terms/apple-developer-program-license-agreement/
- On Apple's subscriptions page: "During a subscriber's first year of service, you receive 70% … After a subscriber accumulates one year of paid service, your net revenue increases to 85%." The rules on that page:
  - Free trials and renewal extensions don't count as days of paid service.
  - Days of paid service are counted per subscription group.
  - Upgrades, downgrades and crossgrades within a group don't reset the count.
  - A lapse of up to 60 days pauses the count rather than resetting it.

  https://developer.apple.com/app-store/subscriptions/
- **Small Business Program (SBP): 15%** on paid apps and all IAP, from the first billing cycle. Who qualifies: developers with no more than $1M in proceeds (counted with Associated Developer Accounts) in the prior calendar year, plus developers new to the store. You must enroll. If you cross $1M during a year, the standard rate applies "to future sales" for the rest of that year. Sources: https://developer.apple.com/app-store/small-business-program/ and DPLA Schedule 2 §3.4(b).
- Apple's subscriptions page: "If you're currently enrolled in the App Store Small Business Program, you receive 85% … regardless of whether or not the subscription has accumulated one year of paid service." The US has no further drop below 15%. The 10% tier on the SBP page applies to EU alternative terms only.

**What changed in 2025–2026, and whether it applies to FTF**
- **US link-out purchases: Apple charges 0% today** (see §2). This is the only US change that matters to FTF.
- China: Apple cut the SBP, Mini Apps and post-year-one subscription rates to 12%, effective 2026-03-15. This is secondary reporting; Apple's notice is "Adjustments to the China storefront" (2026-03-12, https://developer.apple.com/news/?id=dadukodv). **Does not apply** to FTF.
- EU: new Attachment 14 terms took effect 2026-10-01 (https://developer.apple.com/news/?id=0cgo95n6). Brazil terms: https://developer.apple.com/news/?id=umq9wxmm. Japan terms: https://developer.apple.com/news/?id=76371du6. **None apply** to a US-only app.
- The 2026-10-13 DPLA update (https://developer.apple.com/news/?id=17mwd36z) added three things:
  - Group Purchases / multiseat terms.
  - Reporting of tax data to tax authorities.
  - Limits on how developers may use customer tax data.

  No US commission change.
- The December 2025 DPLA update added Apple's "right to offset or recoup amounts owed" and clarified consumer-protection requirements in Schedules 2/3 (https://developer.apple.com/news/?id=76371du6).

**Proceeds per FTF SKU at 15% (SBP) and 30%** (commission is taken on price net of tax):

| SKU | Price | Net at 15% | Net at 30% |
|---|---|---|---|
| Pro monthly | $4.99 | $4.24 | $3.49 |
| Pro annual | $34.99 | $29.74 | $24.49 |
| Season Pass | $19.99 | $16.99 | $13.99 |
| Rookie Pass | $9.99 | $8.49 | $6.99 |
| Founder | $99 / $119 | $84.15 / $101.15 | $69.30 / $83.30 |
| Tips | $1.99 / $4.99 / $9.99 | $1.69 / $4.24 / $8.49 | — |

---

## 2. US external-purchase links (Epic v. Apple)

### Timeline (primary sources where available)
- **2024-01-18:** Apple's first US "StoreKit External Purchase Link Entitlement":
  - one plain link;
  - **27%** commission on purchases made within 7 days of a link tap;
  - **12%** for SBP members and for subscriptions after year one.

  Secondary source: https://mjtsai.com/blog/2024/01/18/storekit-purchase-link-entitlement-for-united-states/ (published 2024-01-18). **Historical; not in force.**
- **2025-04-30:** N.D. Cal. (Judge Gonzalez Rogers) found Apple in civil contempt. The order "permanently barred Apple from '[i]mposing any commission or any fee on purchases that consumers make outside an app'". It also barred most of Apple's link design and placement conditions. This is quoted from Apple's own SCOTUS stay application at App. 133a: https://www.supremecourt.gov/DocketPDF/25/25A1213/407958/20260504154515930_2026-05-04%20Apple-Epic%20SCT%20Application%20to%20Stay%20Mandate.pdf (filed 2026-05-04).
- **2025-05-01:** Apple updated Guidelines 3.1.1, 3.1.1(a), 3.1.3 and 3.1.3(a) "for compliance with a United States court decision regarding buttons, external links, and other calls to action." https://developer.apple.com/news/?id=9txfddzf
- **2025-06:** The Ninth Circuit denied Apple a stay (per Courthouse News, below).
- **2025-12-11:** Ninth Circuit, No. 25-2935 (161 F.4th 1162). Opinion: https://law.justia.com/cases/federal/appellate-courts/ca9/25-2935/25-2935-2025-12-11.html. I could not fetch it directly; the holdings below come from Apple's filing and law-firm summaries.
  - **Affirmed** the contempt finding. The 27% commission was "prohibitive" in effect.
  - **Reversed** the outright zero-commission ban as punitive. Apple "should be able to charge a commission on linked-out purchases based on the costs that are genuinely and reasonably necessary for its coordination of external links for linked-out purchases, but no more" (App. 45a).
  - Pending remand: "Apple should not be able to charge any commission for linked-out purchases until such time as the district court has approved an appropriate fee" (App. 46a). Both quotes come from Apple's stay application above.
  - Allowed Apple to stop developer links from being **more prominent** than Apple's own purchase options (fonts, sizes, placement). Developers may match Apple's own styling. Upheld the ban on Apple messaging that deters users from leaving the app. Source: Fenwick, published 2025-12-22, https://www.fenwick.com/insights/publications/ninth-circuit-largely-upholds-ruling-in-epic-v-apple
  - A permitted fee may include some compensation for IP directly used in linked-out purchases, but not "security and privacy features." Source: SCL LLP, published 2025-12-29, https://scl-llp.com/ninth-circuit-upholds-apple-contempt-finding-but-narrows-scope-of-remedial-relief/
  - Affirmed that the injunction covers **all** developers on the US storefront, not just Epic (stay application pp. 13–14).
- **2026-03-30:** The Ninth Circuit denied rehearing (SCOTUS docket, below).
- **2026-05-06:** SCOTUS denied Apple's application to stay the mandate (25A1213). The case returned to the district court. https://www.cnbc.com/2026/05/06/supreme-court-declines-to-pause-order-holding-apple-in-contempt-in-epic-games-lawsuit.html
- **2026-06-30: SCOTUS granted cert in No. 25-1311, limited to Question 1:** "Whether a court may hold a party in civil contempt based on a violation of an injunction's 'spirit' where the injunction is silent as to the conduct …". Question 2, Apple's CASA/universal-injunction challenge, was **not** granted, so the all-developer scope stands. QP: https://www.supremecourt.gov/qp/25-01311qp.pdf. Docket: https://www.supremecourt.gov/search.aspx?filename=/docket/docketfiles/html/public/25-1311.html
- **2026-08-11:** The district court denied Apple's motion to stay the remand. Gonzalez Rogers: "The court is to determine an appropriate commission, that is a factual issue." Courthouse News, published 2026-08-11: https://www.courthousenews.com/apples-fight-over-commissions-for-linked-out-app-store-purchases-continues-in-federal-court/
- **2026-08-13:** Justice Kagan denied a second stay application (26A194) (docket).
- **~2026-08-13: Apple's remand proffer proposes:**
  - **15%** on US linked-out purchases for standard apps;
  - **10%** for subscription renewals and for the Video, News and Mini Apps partner programs;
  - **5%** for SBP members.

  Source: 9to5Mac, published 2026-08-13, https://9to5mac.com/2026/08/13/apple-proposes-commissions-of-up-to-15-for-off-app-store-purchases-in-the-us/. Epic's position is that the cost-based standard points to roughly zero. Secondary source; I did not see the proffer itself.
- **2026-09-14:** Apple filed its merits brief. **Epic's brief is due 2026-11-13; Apple's reply 2026-12-14.** No argument date is set on the docket. Press expects argument in early 2027 and a decision by about June 2027 **[unverified expectation]**. https://www.macobserver.com/news/apple-epic-oral-argument-why-not-before-2027/

### Current guideline wording for the US storefront
Verbatim from https://developer.apple.com/app-store/review/guidelines/ ("Last Updated: June 8, 2026").

> **3.1.1 In-App Purchase:** If you want to unlock features or functionality within your app, (by way of example: subscriptions, in-game currencies, game levels, access to premium content, or unlocking a full version), you must use in-app purchase. Apps may not use their own mechanisms to unlock content or functionality, such as license keys, augmented reality markers, QR codes, cryptocurrencies and cryptocurrency wallets, etc.
> Apps may use in-app purchase currencies to enable customers to "tip" the developer or digital content providers in the app.
> Any credits or in-game currencies purchased via in-app purchase may not expire, and you should make sure you have a restore mechanism for any restorable in-app purchases.
> … Apps may allow users to browse NFT collections owned by others, provided that, except for apps on the United States storefront, the apps may not include buttons, external links, or other calls to action that direct customers to purchasing mechanisms other than in-app purchase.

> **3.1.1(a) Link to Other Purchase Methods:** Developers may apply for entitlements to provide a link in their app to a website the developer owns or maintains responsibility for in order to purchase digital content or services. These entitlements are not required for developers to include buttons, external links, or other calls to action in their United States storefront apps. …
> StoreKit External Purchase Link Entitlements: … In all other storefronts, except for the United States storefront, where this prohibition does not apply, apps and their metadata may not include buttons, external links, or other calls to action that direct customers to purchasing mechanisms other than in-app purchase.
> … If your app engages in misleading marketing practices, scams, or fraud in relation to the entitlement, your app will be removed from the App Store and you may be removed from the Apple Developer Program.

> **3.1.3 Other Purchase Methods:** The following apps may use purchase methods other than in-app purchase. Apps in this section cannot, within the app, encourage users to use a purchasing method other than in-app purchase, except for apps on the United States storefront and as set forth in 3.1.1(a) and 3.1.3(a). Developers can send communications outside of the app to their user base about purchasing methods other than in-app purchase.
> **3.1.3(b) Multiplatform Services:** Apps that operate across multiple platforms may allow users to access content, subscriptions, or features they have acquired in your app on other platforms or your web site, including consumable items in multi-platform games, provided those items are also available as in-app purchases within the app.

### Can FTF link to a web checkout today, at what fee, and with what risk?
- **Yes, in the App Store (production) build on the US storefront.** No entitlement is needed and Apple charges **0%** commission today. Apple told SCOTUS it "will continue to forgo charging a commission while its petition remains pending and throughout any proceedings in this Court" (stay application). RevenueCat's docs say the same: "iOS developers are now permitted to guide users to web-based payment flows without additional Apple fees or restrictive design requirements." https://www.revenuecat.com/docs/web/overview
- **[interpretation]** Keep IAP offered alongside the web link. 3.1.1 still says unlocking features "must use in-app purchase," and 3.1.3(b) lets web-bought access carry into the app only if those items are "also available as in-app purchases within the app." The US carve-outs cover calls to action, not the IAP requirement itself.
- **Not from a TestFlight build.** DPLA §7.4: "Any digital purchases offered in Your Application distributed through TestFlight (whether through the In-App Purchase API or otherwise), or resulting immediately from a link out of such Application, must be for no charge to the end user and must be for beta testing purposes only." This clause was clarified in June 2025 (https://developer.apple.com/news/?id=r9dcmrvs). See the implications at the end.
- **Fee stack for a web sale** (see §7):
  - Stripe: 2.9% + 30¢.
  - RevenueCat: 1% of MTR once above $2.5k.
  - Sales tax becomes FTF's responsibility, because Apple remits US tax only on its own sales.
- **Litigation risk timeline [interpretation]:**
  - *Near term (now to the decision, likely by mid-2027):* 0% stays. Any fee the district court approves applies only from approval onward, per the Ninth Circuit language above. I found no source that addresses retroactive charging, so a retroactive fee looks unlikely but is not ruled out.
  - *Remand outcome (no hearing date found):* a cost-based fee. Apple's opening ask is 15%, or 5% for SBP. Epic argues for near zero.
  - *SCOTUS outcome (decision ~June 2027):* if Apple wins Question 1, the contempt basis for the commission limits could fall. The 2021 injunction text never mentions commissions, so Apple could try to reinstate something like its 2024 27%/12% link-out framework. That would be **2027 at the earliest**. The anti-steering injunction itself (links allowed) and its all-developer scope are not under review.
  - *Practical read:* treat 0% on web as a temporary arbitrage. Build the web path so it can be switched off, and don't price the web Founder assuming 0% Apple forever.

---

## 3. StoreKit product-type fit

### Season Pass: non-consumable vs non-renewing subscription
- Apple's type definitions (https://developer.apple.com/help/app-store-connect/reference/in-app-purchase-types):
  - **Non-Consumable:** "A product that is purchased once and does not expire or decrease with use."
  - **Non-Renewing Subscription:** "A product that allows users to purchase a service with a limited duration. … This type of Subscription does not renew automatically."
- DPLA Attachment 2 §2.3: "Other than specific approved rental content such as films, television programs, music, books, rentals of content, services or functionality through the In-App Purchase API are not allowed (e.g., use of particular content may not be restricted to a pre-determined, limited period of time)." Content and services "may be offered … on a subscription basis."
- Guideline **3.2.1(iii)** lists as acceptable: "Disabling access to specific approved rental content … after the rental period has expired; all other items and services may not expire."
- **Conclusion:** a "Pro for one season" product that switches off at season end must be a **non-renewing subscription**, not a non-consumable. This conflicts with the current plan. A year-labelled non-consumable would comply only if it permanently unlocked something tied to the 2026 season, for example permanent access to 2026-season tools or data. It cannot be time-limited Pro.
- Non-renewing obligations:
  - The original StoreKit API docs say: "When a customer purchases an auto-renewable or non-renewing subscription, your app is responsible for making it available across all the person's devices, and for restoring past purchases." https://developer.apple.com/documentation/storekit/original-api-for-in-app-purchase
  - StoreKit 2 `Transaction.currentEntitlements` returns "The latest transaction for each non-renewing subscription, including finished ones." The App Store does not track expiry; FTF computes the end date from the purchase date. https://developer.apple.com/documentation/storekit/transaction/currententitlements
  - The Attachment 2 §2.6 cross-device rule also applies: non-consumables must be "available to all of the devices associated with an end user's account."
  - Non-renewing subscriptions get **no intro offers or free trials** (those exist only for auto-renewables) and no 85% after-year rate. That matters little under SBP.
  - The first non-renewing subscription must be submitted with a new app version (https://developer.apple.com/help/app-store-connect/manage-in-app-purchases/create-non-renewing-subscriptions).
- **RevenueCat gotcha:** any non-subscription product attached to an entitlement unlocks it "forever." https://www.revenuecat.com/docs/platform-resources/non-subscriptions. RevenueCat community guidance for non-renewing products: either keep them off entitlements and compute expiry from the purchase date, or grant a time-boxed promotional entitlement from a webhook. **[community source, not official docs]**
- **Disclosure:** state the hard end date. A pass bought in October covers about 4 months of the NFL season. Guideline 5.6 bars tricking users into purchases.

### Founder lifetime as a non-consumable
- A good fit: purchased once, never expires, restorable via StoreKit. RevenueCat recommends exactly this: "create a new **non-consumable** IAP … and add the product to your entitlement" (non-subscriptions doc above).
- A cap of 100 is not a StoreKit feature. Enforce it server-side, then remove the product from sale (or hide it) when sold out. Scarcity copy must stay truthful (5.6).
- **[unverified applicability]** For one-time digital-content IAPs on the US storefront, DPLA Attachment 2 §3.2 now requires stating that the buyer is "buying or purchasing a license." Its examples are media (books, music, video), not app features. Still, define "lifetime" in the Terms of Use (lifetime of the product).

### Family Sharing
- Available only for auto-renewable subscriptions and non-consumables, shared with up to five family members. "Once you turn on Family Sharing for an In-App Purchases … you can't turn it off." https://developer.apple.com/help/app-store-connect/configure-in-app-purchase-settings/turn-on-family-sharing-for-in-app-purchases and https://developer.apple.com/documentation/storekit/supporting-family-sharing-in-your-app
- Non-renewing subscriptions and consumables can't be family-shared (by omission from both lists).
- Implication: a family-shared Founder could entitle up to 6 Apple IDs per unit, which undermines a cap of 100. If enabled, FTF must handle `REVOKE` notifications. Recommend leaving it **off** (the default).

### Upgrade, downgrade and crossgrade within one group
From https://developer.apple.com/app-store/subscriptions/ and DPLA Schedule 2 §3.8(a):
- **Upgrade** (higher level): immediate, with a prorated refund of the old plan.
- **Downgrade:** takes effect at the next renewal.
- **Crossgrade** (same level): immediate if the durations match. With different durations, for example monthly to annual at the same level, it takes effect at the next renewal date.
- Users can change "as often as they like" in Settings, and apps can call `showManageSubscriptions(in:)`.
- Guideline **3.1.2(b):** "Users should have a seamless upgrade/downgrade experience and should not be able to inadvertently subscribe to multiple variations of the same thing."
- FTF decision: if monthly and annual sit at the same level, a monthly-to-annual switch waits for the next renewal. Rank annual higher only if an immediate switch (with proration) is wanted.

### Non-consumable "Pro forever" alongside an active subscription (double pay)
- Apple does not cancel an auto-renewable when a non-consumable is bought, and developers cannot cancel a user's subscription. RevenueCat staff: "Purchasing a non-consumable product will not automatically cancel an active subscription, so you'll need to inform your user that they need to cancel." https://community.revenuecat.com/general-questions-7/what-happens-if-a-subscribed-user-purchases-lifetime-access-1156 (older thread, ~2021)
- RevenueCat's own guide (published 2025-11-12): moving to lifetime "usually requires customers to cancel their existing subscription manually … can be confusing, sometimes leading to accidental double payments." https://www.revenuecat.com/blog/growth/lifetime-subscriptions
- Common handling:
  1. Check `CustomerInfo` before showing Founder or Season Pass.
  2. If an auto-renewal is active, show a warning and a pre-purchase explainer.
  3. After purchase, deep-link to `showManageSubscriptions`.
  4. Point users to Apple's refund flow (`beginRefundRequest`) for overlap.
- The same applies to Season Pass bought during an active auto-renewal. Non-renewing products are not in the subscription group, so StoreKit will not block the overlap.

---

## 4. Offers

### Introductory offers
- Free-trial durations allowed: **3 days, 1 or 2 weeks, 1, 2, 3 or 6 months, 1 year**, for every standard duration. Pay-as-you-go and pay-up-front have their own lists. https://developer.apple.com/help/app-store-connect/manage-subscriptions/set-up-introductory-offers-for-auto-renewable-subscriptions
- So **14 days is "2 weeks" (OK). "30 days" doesn't exist; it must be configured and described as "1 month."**
- "Each person is only eligible to redeem one introductory offer per subscription group." Example from Apple: a customer who uses a free trial and then upgrades to another product in the same group with its own trial "aren't eligible for the second offer" (same page).
- One current and one future intro offer per storefront. An intro offer can't be edited; delete and recreate it.

### Promotional offers
- For existing or lapsed subscribers only. The developer sets eligibility, and a server-generated signature is required for each redemption. "Customers can accept the offer even if they've already accepted an introductory offer."
- **Up to 10 active offers per subscription.** Types: free, pay-as-you-go, or pay-up-front. They apply to all storefronts.
- Sources: https://developer.apple.com/help/app-store-connect/manage-subscriptions/set-up-promotional-offers-for-auto-renewable-subscriptions and https://developer.apple.com/documentation/storekit/implementing-promotional-offers-in-your-app
- Users confirm through Apple's purchase sheet.
- **[unverified]** For an active subscriber redeeming an offer on their current product, I did not confirm whether it starts immediately or at the next renewal. Test in sandbox.

### Offer codes
- Subscriptions (https://developer.apple.com/help/app-store-connect/manage-subscriptions/set-up-subscription-offer-codes):
  - Up to **1M redemptions per app per quarter**, shared across subscriptions.
  - **10 active offers per subscription SKU.**
  - One-time-use codes are made in batches of 500–25,000 and expire within 6 months. Custom codes allow up to 25,000 redemptions per batch, and expiry is optional.
  - Eligibility can be new, existing and/or expired subscribers.
  - "Customers are limited to redeeming one code per offer."
  - A code can be set **not** to auto-renew (free offers only), which makes a commitment-free trial.
  - Existing subscribers can redeem only codes at their level or an upgrade (subscriptions page).
- Offer codes now also cover **consumables, non-consumables and non-renewing subscriptions**: 10 active offers per app, 1M codes per quarter, and in-app redemption needs iOS 16.3+. https://developer.apple.com/help/app-store-connect/manage-in-app-purchases/create-offer-codes-for-in-app-purchases
- Apple explicitly endorses referral use: "Create a peer-to-peer member referral program that enables current subscribers to share an offer code and receive a benefit for promoting your app. You are responsible for distributing any benefits or rewards to subscribers." https://developer.apple.com/app-store/subscriptions/
- WWDC26: the offer-code redemption sheet now returns a `VerificationResult`. RevenueCat, published 2026-06-09: https://www.revenuecat.com/blog/engineering/wwdc26-whats-new-for-apps

### Win-back offers
- The in-app win-back sheet appears automatically on **iOS 18 / iPadOS 18 / macOS 15+**. Offers also show in Manage Subscriptions on iOS 14.3+, and can be promoted on the App Store. https://developer.apple.com/help/app-store-connect/manage-subscriptions/set-up-win-back-offers
- Configured per product, not per group. Eligibility settings:
  - minimum paid duration of 1–24 months, or 3, 4 or 5 years;
  - lapsed for between 1 and 24 months;
  - optional wait of 2–24 months between offers.
- Limits: up to 350 offers per subscription, 5 active per storefront per subscription. Offers must run at least 3 days. Requires a subscription already approved by App Review.

### Server-side "free month" grant (not via StoreKit)
- **[interpretation] Allowed in practice. I found no guideline text that bans it.**
  - 3.1.1 bans the developer's "own mechanisms to unlock content or functionality, such as license keys … QR codes". It targets selling or unlocking outside IAP, not free grants.
  - Apple's subscriptions page expects developers to distribute referral rewards themselves.
  - RevenueCat supports "granted/promotional entitlements" through the REST API, server-side only (secret key). These "never cancel a user's subscription, charge a user, issue a refund, or convert to a paid subscription." https://www.revenuecat.com/docs/dashboard-and-metrics/customer-profile
- Risk points:
  - A user-typed **code** box that unlocks Pro looks like a "license key." Prefer an automatic server grant, or use Apple offer codes for anything code-based.
  - Describe the referral flow in the Review Notes. Guideline 2.3.1(a): "All new features, functionality, and product changes must be described with specificity in the Notes for Review section."

### Extending an existing subscriber's paid period as a referral reward
| Mechanism | Works for active payers? | Limits | Fit for repeatable give-get |
|---|---|---|---|
| RevenueCat promotional entitlement | Grants access, but the Apple subscription keeps billing on schedule, so a paying user gains nothing | None at Apple | Good for **free/lapsed** users; meaningless for active payers |
| Promotional offer (free 1 month) | Yes; the user taps through the Apple sheet | 10 active offers per subscription; signature per redemption | Best StoreKit-native option for active subscribers **[timing unverified]** |
| Offer codes | Yes (existing subscribers, same or higher level) | **One code per offer per customer**; 10 active offers | Poor for repeat rewards |
| Renewal Date Extension API | Yes, paid and active only; not during a free trial | **Twice per 365 days per customer, each ≤90 days**; irreversible; Apple emails the customer; days don't count toward the 85% year | Apple frames it for outages and canceled events ("Use this endpoint to compensate your customers for temporary service outages, canceled events, or interruptions"). RevenueCat says promotional use is "unclear … Use at Your Own Discretion" |

Sources:
- https://developer.apple.com/documentation/appstoreserverapi/extend-a-subscription-renewal-date
- https://developer.apple.com/documentation/appstoreserverapi/extending-the-renewal-date-for-auto-renewable-subscriptions
- https://www.revenuecat.com/docs/guides/promotional-subscription-extensions
- https://www.revenuecat.com/blog/growth/how-to-build-a-referral-program-for-mobile-apps

---

## 5. Guidelines touching referral rewards (current text)

- **3.2.2(x)** (added 2025-06-09; the text was moved from old 3.1.2(a) bullet 5 and Apple "permits developers to otherwise incentivize users to take specific actions within app," per https://developer.apple.com/news/?id=r9dcmrvs):
  > (x) Apps must not force users to rate the app, review the app, download other apps, or other store-related actions in order to access functionality, content, or use of the app. Apps may otherwise incentivize users to take specific actions within apps (e.g. completing a level, watching an ad).
- **3.1.2(a)** (paid subscribers must not have to do extra tasks):
  > As with all apps, those offering subscriptions should allow a user to get what they've paid for without performing additional tasks, such as posting on social media, uploading contacts, checking in to the app a certain number of times, etc.
- **3.1.2(a)** (business-model change):
  > If you are changing your existing app to a subscription-based business model, you should not take away the primary functionality existing users have already paid for.
- **3.1.2(c)** (disclosure):
  > Before asking a customer to subscribe, you should clearly describe what the user will get for the price. … Ensure you clearly communicate the requirements described in Schedule 2 of the Apple Developer Program License Agreement.

  DPLA Schedule 2 §3.8(b) requires clear and conspicuous disclosure of:
  - the title;
  - the length;
  - the price, and price per unit if appropriate;
  - in-app links to the Privacy Policy and Terms of Use.

  §3.8(c) adds that you "must fulfill the offer during the entire subscription period, as marketed."

  Apple's subscriptions page adds required sign-up-screen elements:
  - name, duration and content;
  - "Full renewal price, shown clearly and prominently";
  - a sign-in/restore path;
  - the billed amount as "the most prominent pricing element";
  - for trials, "how long the free trial lasts and the price billed once the free trial is over."
- **3.1.2(a)** (scams):
  > Apps that attempt to scam users will be removed … This includes apps that attempt to trick users into purchasing a subscription under false pretenses or engage in bait-and-switch and scam practices …
- **5.6 Developer Code of Conduct:**
  > Apps should never prey on users or attempt to rip off customers, trick them into making unwanted purchases, force them to share unnecessary data, raise prices in a tricky manner, charge for features or content that are not delivered, or engage in any other manipulative practices within or outside of the app.
- **5.6.3 Discovery Fraud:**
  > Manipulating any element of the App Store customer experience such as charts, search, reviews, or referrals to your app erodes customer trust and is not permitted.
- **5.1.2(v)** (contact-based invites):
  > Do not contact people using information collected via a user's Contacts or Photos, except at the explicit initiative of that user on an individualized basis; do not include a Select All option or default the selection of all contacts. You must provide the user with a clear description of how the message will appear to the recipient before sending it …
- **5.1.1(v)** says "inviting friends to use the app" is not core functionality, so it can't be the reason to force a login.
- **"Invite friends to unlock":** no guideline names it.
  - **[interpretation]** Since June 2025, 3.2.2(x) allows incentivizing in-app actions.
  - The reward must not depend on store actions like ratings or reviews. It must not take away what a payer already bought (3.1.2(a)). It must not look like gaming installs (5.6.3).
  - FTF's gate (leaguemate joined and did ≥25 ranking actions, granted server-side, never on install) fits that reading better than install-based rewards.
  - Locking a feature behind invites *only*, when the same feature is otherwise sold, is untested. Keep invite rewards as extra time, not the sole path.

---

## 6. Price changes and grandfathering

Source: https://developer.apple.com/help/app-store-connect/manage-subscriptions/manage-pricing-for-auto-renewable-subscriptions, plus the subscriptions page and DPLA Schedule 2 §3.9.

- **Consent is required if any of these applies:**
  1. The subscriber's region requires consent for any price change.
  2. "The price increase is more than 50% of the current price **and** the difference in price exceeds approximately US$5 per period for non-annual subscriptions, or US$50 per year for annual subscriptions."
  3. "The subscriber experienced a price increase for that subscription within the past 12 months."
- **Otherwise it's notice only.** Apple emails and pushes 27 or 7 days before renewal, and shows in-app messaging on iOS 13.4+.
- **Consent requests** start 60 days before renewal for plans of 2 months to annual, 27 days for monthly, and 7 days for weekly. They repeat about weekly. Non-responders expire at the end of the current period.
- **Minimum notice:** 7 days (weekly), 27 days (monthly), 30 days (longer plans). Inside that window, users renew once more at the old price.
- Users on intro or promo pricing, including free trials, "will renew for at least one more renewal period at the price that was displayed when they subscribed."
- One scheduled change per storefront per billing plan type. A new increase can overwrite a pending one. Increases can't be reversed once in effect.
- **Grandfathering:**
  - Option A, "Keep the current price for existing subscribers." Apple allows "an unlimited number of active subscribers at their existing price." Lapsed users can resubscribe at the preserved price within 60 days.
  - Option B applies the new price to existing subscribers.
  - **Price decreases always pass through:** "You don't have the option to preserve the higher price for existing subscribers."
- FTF arithmetic:
  - $4.99 to $9.99 monthly is +100% but exactly +$5.00, which is at the "approximately US$5" line. App Store Connect shows per storefront whether consent is needed.
  - $34.99 to $49.99 annual is +43%, so notice only, unless a raise happened within the previous 12 months.
  - 5.6 still bans raising prices "in a tricky manner."
- Context **[lower confidence; vendor source]:** the FTC "click-to-cancel" rule was vacated by the Eighth Circuit in July 2025. ROSCA and state auto-renewal laws still apply. https://subtracker.io/best/subscription-cancellation-rights-us-federal

---

## 7. Fees beyond Apple

- **RevenueCat** (https://www.revenuecat.com/pricing/):
  - "Pay nothing for up to $2,500 in monthly tracked revenue. Then pay 1% of what you track once you hit $2,500 in MTR."
  - Docs: "MTR … includes the revenue from all purchases and renewals" and "is measured before store commission and taxes." https://www.revenuecat.com/docs/welcome/set-up-revenuecat/account-management
  - The wording implies 1% of *all* tracked revenue once over $2.5k, not just the excess. The pricing FAQ answer wasn't visible, so **[unverified]**.
  - Web (Stripe) purchases tracked in RevenueCat count toward MTR by the "all purchases" definition **[inferred]**.
  - RevenueCat Billing uses "Stripe as the payment gateway" (web overview doc), so Stripe fees still apply.
- **Stripe US** (https://stripe.com/pricing):
  - **2.9% + 30¢** per successful domestic card charge. Surcharges: +0.5% manually entered, +1.5% international cards, +1% currency conversion.
  - Stripe Billing pay-as-you-go is **0.7%** of billing volume, for recurring web subscriptions.
  - Stripe Tax is **0.5%** per transaction where registered (no-code), or $0.50 per transaction via API.
  - Checkout and Payment Links: no extra fee.
  - Worked examples: $99 Founder costs ~$3.17 (3.2%); $19.99 costs ~$0.88 (4.4%); $1.99 costs ~$0.36 (18%). Tips are bad on Stripe; keep them in IAP.
- **US sales tax:** DPLA Schedule 2 §3.2 hands responsibility to Exhibit B. Exhibit B §1, "Apple shall collect and remit to the competent tax authorities the taxes …," lists the **United States** with no footnote (DPLA, Schedules last updated 2026-10-13). So **Apple collects and remits US sales tax on IAP**. On **web/Stripe sales FTF is the seller** and owns sales-tax nexus and remittance; Stripe Tax is optional. **[Thresholds per state not researched.]**

---

## 8. Benchmarks

Main source: **RevenueCat, State of Subscription Apps 2026 (SOSA 2026).** It covers 115,000+ apps, $16B revenue and 1B+ transactions; metrics are for 2025. https://www.revenuecat.com/state-of-subscription-apps. The summary blog was published 2026-03-19 and updated 2026-09-11: https://www.revenuecat.com/blog/growth/subscription-app-trends-benchmarks-2026. Sports sits inside **"Media & Entertainment"** (with Entertainment, Music, News). Most interactive chart values were not readable; the figures below are the report's own text callouts.

### Price points (2025 data)
- **All categories:**
  - Weekly median $5–$5.90 (most common $5).
  - **Monthly median rose $7 to $8** (most common $10).
  - **Yearly median rose $31.60 to $34.80** (most common $30).
  - P90 yearly is about $90.
- **North America:** monthly median **$9.99**, yearly median **$39.99**.
- **By category:** monthly medians $4.99–$9.99 (Education, Health and Social at $9.99; Gaming $4.99); yearly medians $20–$44.99 (Education $44.99, Health & Fitness ~$39.94, Gaming $24.99, Travel $20). Media & Entertainment's median wasn't given in text **[gap]**.
- **FTF comparison [computed]:**
  - FTF's $4.99 monthly is at the bottom of the category range.
  - $34.99 annual equals the all-app median but sits below the NA median.
  - FTF's annual is 58% of 12× monthly (a 42% discount). The median app's annual is about 36% of 12× its monthly (a ~64% discount), and NA's about 33%.
  - So FTF's monthly is cheap *relative to* its annual. The annual pitch is weaker than typical.

### Trial length vs trial-to-paid
- SOSA 2026 median trial-to-paid: **≤4 days 25.5%; 5–9 days 37.4%; 17–32 days 42.5%** (10–16 days ~35.4%, wide spread). NA median trial-to-paid is 34.2%.
- 46.5% of apps now use trials of 4 days or less.
- Day-0 cancellations: 55.4% of 3-day-trial cancels, 35.7% of 14-day, 31.1% of 30-day.
- RevenueCat "How long should your free trial be?" (17,000+ apps, published **2026-09-28**), https://www.revenuecat.com/blog/growth/free-trial-length:
  - **Monthly plans:** conversion is 39.6% (≤4 days), 45.9% (5–9), **46.6% (10–16)** and 43.7% (17–32). First renewal among payers is 54.2%, 62.8%, **72.0%** and 77.5%.
  - **Annual plans:** conversion is 24% (≤4 days), 33% (5–9), 43% (10–16) and **44.6% (17–32)**. First renewal is 18.3%, 25.3%, 36.4% and **47.5%**.
  - These are correlational, as RevenueCat warns. They support FTF's 14-day monthly and ~1-month annual trials.

### Install-to-paid: hard paywall vs freemium
- Day-35 download-to-paid median: **hard paywall 10.7%** (P90 38.7%) vs **freemium 2.1%**.
- North America median across models is 2.6–2.8%. Media & Entertainment download-to-trial median is 4.0%, and its trial-to-paid spread is the widest of any category (11.5%–69.5%).
- **Year-1 retention is the same** for both models: yearly plans 27% (hard paywall) vs 28% (freemium); monthly 9% vs 8%.
- Revenue per install: hard paywall D14 $2.32 and D60 $3.09, vs freemium D14 $0.27 and D60 $0.38.

### Renewal and churn
- **Annual first renewal: median 23–40% by category** (the summary text also says 24–47%). Second renewal 44–64%, third 56–70%.
- **Monthly renewals:** first 53–61%, second 65–77%, third 73–82%. That implies roughly 39–47% churn at the first monthly renewal, falling to about 18–27% by the third.
- **Year-1 retention, 2024 cohort:** yearly **28%** (down from 31%), monthly **8%** (down from 10%), weekly ~1.2%. Six-month retention of monthly plans: median 14–26%.
- Price effect: high-priced annual plans lose more at the first renewal (37% vs 24% for low-priced) but converge by the third.
- Media & Entertainment shows the widest annual retention variance (~37–68%).
- Timing of annual cancellations: month 1 accounts for 23–50%, months 3–11 for 3–7% each, month 12 for 9–14%.
- Reactivation within a year: **monthly churners 20%** (NA 18%), annual churners ~5%.
- Refunds: NA median **3.4%**; categories 2.5–4.7%.

### Annual vs monthly revenue share
- Sales mix: overall 42% monthly / 34% yearly; North America 36% monthly / 40% yearly.
- Annual's share of durations fell from **41.4% to 33.6%** year over year.
- Revenue: "Monthly subscriptions dominate overall revenue share." Productivity takes ~77–91% of revenue from monthly (the report gives both figures). Health & Fitness takes 59% from annual.
- Revenue per install: annual-dominant apps D60 **$0.46** vs monthly-dominant $0.29 vs weekly-dominant $0.32 vs **lifetime-dominant $0.24**.
- Adapty "State of In-App Subscriptions 2026" (16,000+ apps, $3B, 2025 data): weekly plans' revenue share rose from 43.3% to 55.5%, and there is **no sports category**. Landing page only; https://adapty.io/state-of-in-app-subscriptions-report/ **[summary via ppc.land; full report not read]**.

### Lifetime option on the paywall
- SOSA 2026: **23.2%** of apps run subscriptions plus lifetime (25–29% across regions). Lifetime appears on 5–18% of paywalls (Gaming highest). Lifetime/other is under 5% of sales in every region. Lifetime-dominant apps have the lowest RPI (D14 $0.19, D60 $0.24).
- RevenueCat lifetime guide (published 2025-11-12):
  - Lifetime is "often priced at 5–12x the annual subscription." Examples run from 2.1× to 11.5×.
  - Lifetime "Can cannibalize loyal high-LTV customers."
  - **No quantified lift data.**
  - FTF's Founder at $99–119 is **2.8–3.4× annual**, low compared with that guide's typical range.
- Superwall's "Lifetime or No-Lifetime?" playbook is a how-to only, with no published results (https://superwall.com/solutions/lifetime-or-no-lifetime). **No controlled public data on lifetime lift was found.**

### Seasonal (sports) notes
- **No RevenueCat or Adapty sports-specific seasonal benchmark was found.** Sports isn't broken out; it sits inside Media & Entertainment, which shows the widest variance on both trial conversion and annual retention.
- **[interpretation from the benchmarks above]** For an NFL-cycle product:
  - Monthly plans invite off-season churn. US monthly churners reactivate at 18% within a year.
  - Annual plans hold through the off-season but face a single first-renewal checkpoint (median 23–40%).
  - A non-renewing season pass converts the churn into a deliberate re-purchase.
- Competitors use year-long terms that don't reset at season end (e.g., FF Dataroma $59.99/yr). These come from one search result, not verified on vendor pages.
- New Apple tools from 2026:
  - **Monthly-billed annual (12-month commitment):** announced 2026-04-27 and **not available in the US** ("With the exception of the United States and Singapore"). https://developer.apple.com/news/?id=agq42lxe
  - **Retention Messaging** at cancel time (WWDC26): Apple reported an average +1.4pp save-rate lift, and +5.5pp for promo-offer messages. Per RevenueCat; check availability.
  - **Group Purchases** (multiseat, "launch this winter") could suit league-wide buys. Apple says "**multiseat purchases are enabled by default for subscriptions in App Store Connect**" (2026-09-16). https://developer.apple.com/news/?id=likeohx4

---

## Implications for FTF's SKU plan

1. **Season Pass as a time-limited non-consumable conflicts with Apple's rules.** Non-consumables "do not expire"; DPLA Att. 2 §2.3 bans time-limited rentals of functionality; Guideline 3.2.1(iii) says "all other items and services may not expire." Rebuild `ftf_season_pass_2026` (and any Rookie Pass) as a **non-renewing subscription**. FTF must compute expiry, sync across devices and support restore. Don't attach it directly to the RevenueCat entitlement, which would unlock Pro "forever."
2. **The TestFlight-era Stripe Founder pre-order conflicts with DPLA §7.4.** Any digital purchase offered in a TestFlight build, or "resulting immediately from a link out," must be free. Either sell it only off-app with no link from the beta, or wait for the App Store build. In that build, US link-out is allowed today at 0% Apple commission, and a matching Founder IAP should also exist (3.1.1 / 3.1.3(b)).
3. **"30-day trial" isn't an App Store option.** Configure and label it "1 month." The 14-day trial (2 weeks) is fine.
4. **One intro offer per subscription group.** A user who takes the 14-day monthly trial can't then take the annual trial. Decide which trial to lead with; the data favors leading with annual.
5. **The referral "free month" via server-side entitlement is fine for free or lapsed users but worth nothing to an active payer**, whose Apple subscription keeps billing. For payers, use a free **promotional offer** (10 active offers per subscription, Apple confirmation sheet). Offer codes (one per offer per user) and renewal extensions (2/yr, outage-framed) don't fit repeat rewards. Avoid a user-typed unlock code (3.1.1 "license keys"). Document the flow in Review Notes (2.3.1(a)).
6. **The activation-gated give-get fits 3.2.2(x)** (in-app incentives allowed since 2025-06-09) and avoids 5.6.3 "referrals" manipulation. Keep rewards additive, never required to get what was paid for (3.1.2(a)). Never tie them to ratings or reviews. Contact-picker invites must be one by one, with no Select All (5.1.2(v)).
7. **Founder lifetime: right product type, three issues.**
   - **Double-pay:** Apple won't cancel an active Pro subscription, and you can't. Gate on `CustomerInfo` and route to Manage Subscriptions.
   - **Family Sharing:** leave off. It can't be undone and multiplies seats past the "cap 100."
   - **Cap enforcement:** server-side, then pull the product when sold out.
   - At 2.8–3.4× annual it is priced low against RevenueCat's "often 5–12×" guide.
8. **Tip consumables that grant nothing are explicitly allowed** ("Apps may use in-app purchase currencies to enable customers to 'tip' the developer"). Keep them in IAP; Stripe's 30¢ eats 18% of $1.99.
9. **Enroll in the Small Business Program before the first sale.** That makes it 15% on every SKU from day one, with no further drop after year one in the US. RevenueCat is free under $2.5k MTR, then 1% of tracked revenue including web.
10. **Web checkout is temporary arbitrage, not a pricing base.** Today Apple takes 0%, and Stripe 2.9% + 30¢ plus self-remitted sales tax. Apple has proposed 15% (5% for SBP, 10% for renewals) on remand, with no hearing date. SCOTUS may decide the contempt question by about mid-2027 and could reopen commissions. Build it with a kill switch.
11. **Pricing vs benchmarks.** $4.99 monthly sits at the bottom of category medians (NA median $9.99) and makes the $34.99 annual only a 42% discount, against roughly 64–67% at the median. A later monthly increase to ≥$10 is at the ~$5 consent line; use "preserve price" for grandfathering. Any second raise within 12 months needs consent.
12. **New App Store Connect default to check now:** multiseat (Group Purchases) is **on by default** for subscriptions since 2026-09-16. Turn it off for `ftf_pro_*` until RevenueCat and FTF's entitlement logic support seats. The US-excluded 12-month-commitment plan is not an option.
