# How FINN was built: the prompts behind the customer experience

**Builder:** Abhishek Chhawai (BS, Economics)
**AI tool:** Claude (claude.ai), which wrote, ran and tested the code
**Period:** 31 Oct to 3 Nov 2026

This is the story of the prompts we used to shape FINN around the investor, and what each one changed for the person using the app. Each step ends with a short **Under the hood** note on the technical side.

The question behind every prompt: *an investor opens FINN on their phone. Do they quickly understand what changed, why it matters, and where the proof is?*

---

## 1. Start from the investor's problem, not the technology

**The prompt.** We shared ENAM's two brief documents and asked Claude to build FINN as a research assistant for investors: one search bar where you type a company or a question, with answers taken only from the company's own documents (annual reports, earnings-call transcripts, exchange filings), each one showing where it came from.

**Why.** Investors don't lack information; they drown in it. A trustworthy assistant has to filter the noise and show its sources.

**What the customer gets.** One place to look, and an answer that can be checked.

> **Under the hood:** a Python backend and a React app. Filings come from BSE (NSE blocks cloud servers), prices are end-of-day closes, and Gemini is the AI model.

## 2. "Tell me what matters today": the daily brief (Push)

**The prompt.** We asked for a morning brief that ranks every company announcement by importance, so the few that matter come first and routine paperwork is folded away. Quarterly results should become a simple card, and investors should be able to set alerts for big price moves or unusual trading.

**Why.** A portfolio of 19 holdings can produce dozens of filings a week, and most are compliance noise.

**What the customer gets.**
- A headline like *"2 of 9 filings need you"*.
- Results shown as four key numbers with the change since last quarter and last year.
- Alerts that also say what else happened that day ("why now"), clearly labelled as context rather than cause.

> **Under the hood:** most filings are sorted by simple rules at no cost; only unclear ones go to the AI, in one batch. Alerts are saved and never repeat.

## 3. "Did management keep its word?": research on demand (Pull)

**The prompt.** We asked FINN to compare what management promised on past earnings calls with what the company actually reported, and to check upbeat claims ("a strong quarter") against the real numbers.

**Why.** This is what a sharp analyst does, and what ENAM's brief singled out. It turns long documents into one honest answer.

**What the customer gets.** Clear verdicts: *promise kept*, *nearly kept*, *missed*, *too early to judge*. Each comes with the exact quote and a link to both the transcript page and the results filing.

> **Under the hood:** the AI only finds the quotes; the verdict and the maths are done by plain code, so the AI can't invent an outcome. Expensive analyses run only when the user taps **Run**, and results are saved.

## 4. One connected journey, not separate screens

**The prompt.** With the core in place, we told Claude: *"audit first, don't rebuild."* Make Home, Alerts and Research feel like one product, so an investor can go from an alert to deep research and back without losing their place.

**Why.** Investors think in stories ("this company reported results; is that good?"), not in app modules.

**What the customer gets.**
- A **Research this** button on any filing that opens research with the company and quarter already filled in.
- A **Back to the filing** button to return.
- A price chart you can drag your finger across, and a search box with recent companies.

> **Under the hood:** automated tests click through these journeys on a simulated phone. They caught a real bug: the Ask screen went blank when the AI was unavailable.

## 5. "Make it understandable for a beginner"

**The prompt.** We asked for FINN to work for someone who doesn't know what EBITDA, PAT or YoY mean:
- tap-to-explain financial terms;
- a plain-English mode;
- a short welcome tour;
- every insight answering *What happened? Why does it matter? Where's the proof? What can I do next?*

**Why.** A finance app that needs a finance degree excludes most of the people who need help.

**What the customer gets.**
- **FINN Explain:** tap any dotted word to see *In simple terms / What it is / Why it matters*. There are 44 terms.
- **Plain English / Detailed switch:** numbers become sentences such as *"Profit after tax was ₹120 crore, up 27.7% from a year earlier."*
- **A 3-step welcome tour** and a Help screen.
- **Larger buttons:** 37 were too small for a thumb.

> **Under the hood:** the glossary is prewritten, so it's instant and costs nothing. Plain sentences are generated from the same numbers as the tables, so the two views can never disagree.

## 6. "Let me try it on my phone"

**The prompt.** We asked for a version anyone could open on a phone with no setup.

**What the customer gets.** A single link that opens the full app in any phone browser. Ask FINN answers live through Claude.

> **Under the hood:** the app was packaged as one self-contained web page with its data built in, so no server is needed.

## 7. "Make it look premium"

**The prompt.** We shared a modern fintech app design and asked: *"create the UI like this and keep animating buttons… keep the light and dark theme."*

**Why.** First impressions build trust, and a calm, polished app feels more credible with money.

**What the customer gets.**
- Navy glass cards, company badges and a floating tab bar.
- Buttons that press in, numbers that count up and charts that draw themselves.
- A light/dark theme the app remembers.

All motion switches off for people who prefer reduced motion.

## 8. The turning point: "everything should be real"

**The prompt.** After reviewing the app, we pushed back hard: a demo with fictional companies isn't enough. *"I need the real stock data, and that is easily available on the internet."*

**Why.** An investor can't trust a product that only works on pretend numbers, and ENAM asked for real listed companies.

**What happened.**
- Claude agreed, but refused to put real company names on made-up numbers, since that would mislead a customer.
- It then found an open archive of NSE's official daily price files and downloaded real prices automatically.
- It checked them against an independent website, and they matched exactly (HNGSNGBEES: ₹494.96 and ₹496.38 in June).

**What the customer gets.** Real results. ₹10 lakh invested on 1 Jan 2026 is now **₹9,30,853** (−6.9%), while NIFTY 50 fell **13.6%**. The banner states exactly what data is included and how fresh it is.

> **Under the hood:** a safety check refuses to publish anything that isn't real data. It caught one of Claude's own test databases slipping through, and was tightened.

## 9. "A portfolio like a real investor's"

**The prompt.** Using our own Groww portfolio screens as the reference, we asked for 15 to 20 real holdings, including **gold, debt and international** investments, so global markets are covered too.

**What the customer gets.**
- 19 real holdings: 14 Indian stocks, a gold ETF, two debt ETFs, and US (Nasdaq-100) and Hong Kong ETFs.
- A Groww-style analysis: current value against invested, the comparison with NIFTY 50, and asset and sector allocation.
- For international funds, how the index behind them moved.

The portfolio shows diversification at work: international (+10.5%), gold (+4.9%) and debt (+1.5%) cushioned the fall in stocks.

## 10. "Show me different time horizons, and WhatsApp me"

**The prompt.** We asked to see performance over different periods, and to get WhatsApp messages for important news.

**What the customer gets.**
- **Returns over 1 week, 1 month, 3 months, 6 months, this year and 1 year:** for the portfolio, each asset class, each holding and NIFTY 50, plus each period's best and worst performers.
- **WhatsApp:** a *Share on WhatsApp* button on every alert and filing, plus automatic messages for important events (each sent once, at most 10 a day, never revealing the phone number).

## 11. "Keep the words aligned everywhere"

**The prompt.** We spotted long ticker names such as HNGSNGBEES overlapping their text and asked for correct alignment throughout the prototype.

**What the customer gets.**
- Cleaner rows, where long names have room and amounts never split across lines.
- Corrected small wording issues ("1 of 1 filing needs you").

> **Under the hood:** Claude added a permanent automated check that measures every word on every screen and fails if any text overlaps.

## 12. Ready to share

**The prompt.** *"Host it on Vercel,"* then prepare the GitHub repository, this build history and the covering email.

**What the customer gets.** A public link that works on any phone, with no login and no install.

---

## What the prompts had in common

- **Start from the investor's question:** what changed, why it matters, where's the proof.
- **Audit before adding.** We fixed real gaps instead of piling on features.
- **Plain language first, detail on request.** Beginners and experts read the same facts at different depths.
- **Real data, honestly labelled.** We never let polish stand in for truth.
- **Verify, don't assume:** 79 backend tests, 8 app tests and 16 automated phone walkthroughs passed at the end.

**One honest limit:** live company filings and AI research couldn't run from Claude's environment. They're built and tested, and they run live with the project's daily update job.
