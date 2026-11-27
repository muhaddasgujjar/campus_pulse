import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ListenButton } from "@/components/chat/ListenButton";
import { setSpeaker, Speaker, speechLangOf, spokenText, type SynthLike } from "@/lib/voice/speak";
import { transliterateWord, urduToDevanagari } from "@/lib/voice/urdu";

describe("urduToDevanagari", () => {
  it("reads common answer words correctly from the dictionary", () => {
    expect(urduToDevanagari("داخلے کی آخری تاریخ گزر چکی ہے۔ براہ کرم داخلہ دفتر سے رابطہ کریں۔")).toBe(
      "दाख़िले की आख़िरी तारीख़ गुज़र चुकी है। बराय करम दाख़िला दफ़्तर से राब्ता करें।",
    );
    expect(urduToDevanagari("امتحانی دفتر کا فون نمبر 042-37181828 ہے۔")).toBe(
      "इम्तिहानी दफ़्तर का फ़ोन नंबर 042-37181828 है।",
    );
  });

  it("uses letter rules for other words", () => {
    expect(transliterateWord("لاہوری")).toBe("लाहोरी");
    expect(transliterateWord("باتیں")).toBe("बातें"); // final -یں of plurals and verbs
    expect(transliterateWord("بھائی")).toBe("भाई"); // do-chashmi he makes an aspirate
    expect(transliterateWord("ایک")).toBe("एक");
    expect(transliterateWord("فارمہ")).toBe("फ़ारमा"); // final he after a consonant
  });

  it("keeps Latin words, digits and maps Urdu punctuation and digits", () => {
    expect(urduToDevanagari("BSCS ۲۰۲۶، FY؟")).toBe("BSCS 2026, FY?");
  });
});

describe("Urdu spoken text", () => {
  it("treats Urdu answers with English names as Urdu", () => {
    const answer =
      "BS CS کی فیس (FY 2026-27) فی کریڈٹ گھنٹہ Rs 7,744 ہے، اور داخلہ فیس Rs 17,500 ہے۔ (ماخذ: LGU website, Fee Structure page)";
    expect(speechLangOf(answer)).toBe("ur");
    expect(speechLangOf("Tuition is Rs 7,744 per credit hour (FY 2026-27).")).toBe("en");
  });

  it("drops bracketed source notes and reads Rs as روپے", () => {
    const spoken = spokenText("فیس Rs 7,744 ہے۔ (ماخذ: Fee Structure, LGU website)", true, "ur");
    expect(spoken).toBe("فیس 7,744 روپے ہے۔");
  });

  it("drops list bullets in the middle of an answer", () => {
    expect(spokenText("Fees:\n- Admission fee: Rs 100\n- Misc: Rs 50", false, "en")).toBe(
      "Fees:. Admission fee: rupees 100. Misc: rupees 50",
    );
  });
});

class FakeUtterance {
  voice: SpeechSynthesisVoice | null = null;
  lang = "";
  rate = 1;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public text: string) {}
}

function speakerWith(voices: { lang: string; name: string }[]) {
  const spoken: FakeUtterance[] = [];
  const synth: SynthLike = {
    speak: (u) => void spoken.push(u as unknown as FakeUtterance),
    cancel: () => undefined,
    getVoices: () => voices as SpeechSynthesisVoice[],
  };
  return { speaker: new Speaker(synth, FakeUtterance as unknown as typeof SpeechSynthesisUtterance), spoken };
}

describe("Urdu voice choice", () => {
  afterEach(() => setSpeaker(null));

  it("prefers a real Urdu voice (Edge on Windows, Android)", () => {
    const { speaker, spoken } = speakerWith([
      { lang: "hi-IN", name: "Hindi" },
      { lang: "ur-PK", name: "Urdu" },
    ]);
    expect(speaker.voiceFor("ur")).toMatchObject({ viaHindi: false, voice: { name: "Urdu" } });
    speaker.play("فیس کتنی ہے؟", "ur");
    expect(spoken[0]?.text).toBe("فیس کتنی ہے؟"); // Urdu script as is
  });

  it("falls back to the Hindi voice with Devanagari (Chrome on Windows)", () => {
    const { speaker, spoken } = speakerWith([
      { lang: "en-US", name: "English" },
      { lang: "hi-IN", name: "Google हिन्दी" },
    ]);
    expect(speaker.voiceFor("ur")).toMatchObject({ viaHindi: true });
    speaker.play("فیس کتنی ہے؟", "ur");
    expect(spoken[0]?.text).toBe("फ़ीस कितनी है?");
    expect(spoken[0]?.lang).toBe("hi-IN");
  });

  it("has nothing to offer without Urdu or Hindi voices", () => {
    const { speaker } = speakerWith([{ lang: "en-US", name: "English" }]);
    expect(speaker.voiceFor("ur")).toBeNull();
  });

  it("shows Listen for Urdu answers when the Hindi fallback exists", () => {
    const { speaker } = speakerWith([
      { lang: "en-US", name: "English" },
      { lang: "hi-IN", name: "Hindi" },
    ]);
    setSpeaker(speaker);
    render(<ListenButton text="فیس کتنی ہے؟" hasSources={false} />);
    expect(screen.getByRole("button", { name: "Listen" })).toBeInTheDocument();
  });
});

describe("live answer from Groq (2026-11-27), read by the Hindi voice", () => {
  it("reads every word of a real answer sensibly", () => {
    const answer =
      "یہ اعداد و شمار LGU کی ویب سائٹ کے فیس سٹرکچر صفحے سے 5 اکتوبر 2026 کو تصدیق شدہ ہیں (مالی سال 2026-27)۔";
    expect(urduToDevanagari(answer)).toBe(
      "यह आदाद व शुमार LGU की वेब साइट के फ़ीस स्ट्रक्चर सफ़्हे से 5 अक्टूबर 2026 को तसदीक़ शुदा हैं (माली साल 2026-27)।",
    );
  });
});
