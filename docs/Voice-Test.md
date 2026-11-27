# Campus Pulse AI: Voice Test Sheet (M4, VOI-7)

Purpose: measure, on real devices, how well browser speech works for our students, before we promise anything in the demo. Report the results honestly in `Memory.md` (Section 7, M4), including what does not work.

Time needed: about 30 minutes per device. Two testers: one speaks, one records.

## 1. Devices (test all three)

| # | Device | Browser | Tester | Date |
|---|---|---|---|---|
| A | Android phone (any recent model) | Chrome | | |
| B | Windows laptop | Chrome | | |
| C | Windows laptop | Edge | | |

Write down the phone model and the Android or Windows version.

## 2. Setup

1. Open the chat (the Vercel link, or `http://localhost:3000/chat` on a laptop running `make api-local` and `make web-dev`).
2. Allow the microphone when the browser asks.
3. Use a quiet room first. Repeat phrases 1 to 5 once in a noisy place (corridor or cafeteria) and note the difference.
4. Before each Urdu phrase, choose **اردو** on the recording bar. For the English control phrases choose **EN**.

## 3. What to record for each phrase

| Column | How to fill it |
|---|---|
| Heard | What appeared as the transcript (copy it or take a screenshot) |
| Recognition | **E** exact, **M** minor mistakes but the meaning is right, **W** wrong meaning |
| Answer | **OK** correct answer or a correct "I don't have verified information", **X** wrong answer |
| Seconds | Stopwatch: from tapping send to the first words of the answer (target under 8 s) |

## 4. Phrases

Speak naturally, as a student would. Do not read slowly word by word.

**Urdu (choose اردو)**

| # | Phrase | Heard | Recognition | Answer | Seconds |
|---|---|---|---|---|---|
| 1 | بی ایس سی ایس کی فیس کتنی ہے؟ | | | | |
| 2 | داخلے کی آخری تاریخ کیا ہے؟ | | | | |
| 3 | امتحانی دفتر کا فون نمبر کیا ہے؟ | | | | |
| 4 | داخلہ دفتر کب کھلتا ہے؟ | | | | |
| 5 | کیا آئی کام والے کمپیوٹر سائنس میں داخلہ لے سکتے ہیں؟ | | | | |
| 6 | داخلے کے لیے کتنے نمبر چاہئیں؟ | | | | |
| 7 | بی بی اے کی فیس کتنی ہے؟ | | | | |
| 8 | مین کیمپس کہاں ہے؟ | | | | |
| 9 | اسکالرشپ کیسے ملتی ہے؟ | | | | |
| 10 | کیا ہاسٹل کی سہولت ہے؟ | | | | |
| 11 | داخلہ ٹیسٹ کب ہوتا ہے؟ | | | | |
| 12 | پہلے سمسٹر میں کتنے کریڈٹ آورز ہیں؟ | | | | |
| 13 | اگر میں نے ریاضی نہیں پڑھی تو کیا بی ایس کر سکتا ہوں؟ | | | | |
| 14 | کیا فیس قسطوں میں دی جا سکتی ہے؟ | | | | |
| 15 | السلام علیکم | | | | |
| 16 | شکریہ | | | | |
| 17 | داخلہ دفتر کا ای میل کیا ہے؟ | | | | |
| 18 | کلاسیں کب شروع ہوں گی؟ | | | | |
| 19 | مائیکرو بیالوجی کی فیس کتنی ہے؟ | | | | |
| 20 | مجھے داخلے کے بارے میں مدد چاہیے | | | | |

**English control (choose EN)**

| # | Phrase | Heard | Recognition | Answer | Seconds |
|---|---|---|---|---|---|
| 21 | What are the fees for BSCS? | | | | |
| 22 | When is the last date to apply? | | | | |
| 23 | What is the exam office phone number? | | | | |
| 24 | Can I.Com students apply for computer science? | | | | |
| 25 | Is there a swimming pool on campus? | | | | |

## 5. Spoken replies (Listen)

On each device:

| Check | Result |
|---|---|
| Is the **Listen** button shown for an English answer? Does it sound clear? | |
| Is **Listen** shown for an Urdu answer (ask phrase 1 in Urdu)? If shown, is the Urdu voice understandable? | |
| Which voice read the Urdu answer: a real Urdu voice (Edge: "Microsoft Asad / Uzma … Urdu (Pakistan)"; Android: Google Urdu) or the Hindi voice fallback (Chrome on Windows: "Google हिन्दी", live mode shows a note)? Rate how understandable it is for a Pakistani listener: good / acceptable / poor | |
| Write down any Urdu words the Hindi fallback mispronounces (they can be added to `apps/web/lib/voice/urdu.ts`) | |
| Names of the voices offered (Chrome: open the page, the voice is chosen automatically; note what you hear) | |

The button is hidden on purpose when the device has no voice for the answer's language.

## 6. Live mode (headset icon)

1. Open live mode. Ask phrases 21, 22 and 3 in a row without touching the screen.
2. While an answer is being read, say "wait, what about BBA fees?" Does it stop and answer the new question?
3. Tap the screen while it speaks. Does it stop?
4. Try once without headphones and once with headphones. Note whether the bot interrupts itself (hears its own voice).

| Check | Device A | Device B | Device C |
|---|---|---|---|
| 3 turns in a row worked | | | |
| Interrupting by speaking worked | | | |
| Tapping to interrupt worked | | | |
| Interrupted itself without headphones | | | |

## 7. Summary to copy into Memory.md

- Urdu recognition, per device: number of E, M and W out of 20.
- English recognition, per device: E, M and W out of 5.
- Answer correctness: OK out of 25.
- Voice message time: the slowest of the "Seconds" column (our p95 estimate) per device.
- Urdu voice available for Listen: yes or no, per device.
- Live mode: works / works with headphones only / does not work, per device.
- Decision (Phases.md W9): keep live mode on browser speech, or formally cut it with a note.
