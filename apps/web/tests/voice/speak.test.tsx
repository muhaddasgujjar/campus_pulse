import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ListenButton } from "@/components/chat/ListenButton";
import {
  pickVoice,
  sentences,
  setSpeaker,
  Speaker,
  speechLangOf,
  spokenText,
  type SynthLike,
} from "@/lib/voice/speak";

class FakeUtterance {
  voice: SpeechSynthesisVoice | null = null;
  lang = "";
  rate = 1;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public text: string) {}
}

class FakeSynth implements SynthLike {
  spoken: FakeUtterance[] = [];
  cancelled = 0;
  constructor(private voices: { lang: string; name: string }[]) {}
  speak(utterance: SpeechSynthesisUtterance): void {
    this.spoken.push(utterance as unknown as FakeUtterance);
  }
  cancel(): void {
    this.cancelled += 1;
  }
  getVoices(): SpeechSynthesisVoice[] {
    return this.voices as SpeechSynthesisVoice[];
  }
  /** Finish the utterance being spoken. */
  finishCurrent(): void {
    this.spoken.at(-1)?.onend?.();
  }
}

const EN = { lang: "en-US", name: "Test English" };
const UR = { lang: "ur-PK", name: "Test Urdu" };

function useFakeSpeaker(voices: { lang: string; name: string }[]): FakeSynth {
  const synth = new FakeSynth(voices);
  setSpeaker(new Speaker(synth, FakeUtterance as unknown as typeof SpeechSynthesisUtterance));
  return synth;
}

describe("spoken text (VOI-4)", () => {
  it("leaves out the source line, URLs, markdown and reads Rs as rupees", () => {
    const answer =
      "**Tuition** is Rs 7,744 per credit hour. See https://example.edu/fees\nSource: Test Fee Page · last verified Mon, 5 Oct 2026";
    expect(spokenText(answer, true)).toBe("Tuition is rupees 7,744 per credit hour. See");
  });

  it("keeps passed-date warnings", () => {
    const answer =
      "Last date to apply: Fri, 2 Oct 2026. This date has passed. Please confirm with the Test Office.";
    expect(spokenText(answer, false)).toContain("This date has passed. Please confirm with the Test Office.");
  });

  it("detects Urdu script and splits Urdu sentences", () => {
    expect(speechLangOf("فیس کتنی ہے؟")).toBe("ur");
    expect(speechLangOf("BSCS ki fee kitni hai?")).toBe("en");
    expect(sentences("پہلا جملہ۔ دوسرا جملہ؟")).toEqual(["پہلا جملہ۔", "دوسرا جملہ؟"]);
    expect(sentences("word ".repeat(100), 50).every((s) => s.length <= 50)).toBe(true);
  });

  it("prefers a Pakistani voice, then any voice of the language", () => {
    const voices = [
      { lang: "en-US", name: "US" },
      { lang: "en-IN", name: "India" },
      { lang: "ur_PK", name: "Urdu" },
    ];
    expect(pickVoice(voices, "en")?.name).toBe("India");
    expect(pickVoice(voices, "ur")?.name).toBe("Urdu");
    expect(pickVoice([{ lang: "en-US", name: "US" }], "ur")).toBeNull();
  });
});

describe("Speaker", () => {
  it("speaks sentence by sentence with progress, and stops on demand", () => {
    const synth = new FakeSynth([EN]);
    const speaker = new Speaker(synth, FakeUtterance as unknown as typeof SpeechSynthesisUtterance);
    const progress: number[] = [];
    let ended = 0;
    expect(speaker.play("One. Two.", "en", { onProgress: (p) => progress.push(p), onEnd: () => (ended += 1) })).toBe(true);
    expect(synth.spoken.map((u) => u.text)).toEqual(["One."]);
    synth.finishCurrent();
    expect(synth.spoken.map((u) => u.text)).toEqual(["One.", "Two."]);
    synth.finishCurrent();
    expect(progress.at(-1)).toBe(1);
    expect(ended).toBe(1);
    speaker.play("Three. Four.", "en", { onEnd: () => (ended += 1) });
    speaker.stop();
    expect(ended).toBe(2);
    expect(synth.cancelled).toBeGreaterThan(0);
  });

  it("refuses a language the device has no voice for", () => {
    const speaker = new Speaker(new FakeSynth([EN]), FakeUtterance as unknown as typeof SpeechSynthesisUtterance);
    expect(speaker.play("فیس کتنی ہے؟", "ur")).toBe(false);
  });
});

describe("ListenButton", () => {
  afterEach(() => setSpeaker(null));

  it("plays the spoken version and shows progress until it ends", () => {
    const synth = useFakeSpeaker([EN]);
    render(<ListenButton text={"Rs 1,000 per credit hour.\nSource: Test Page"} hasSources />);
    fireEvent.click(screen.getByRole("button", { name: "Listen" }));
    expect(synth.spoken[0]?.text).toBe("rupees 1,000 per credit hour.");
    expect(screen.getByRole("progressbar", { name: "Playback" })).toBeInTheDocument();
    act(() => synth.finishCurrent());
    expect(screen.getByRole("button", { name: "Listen" })).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("can be stopped", () => {
    const synth = useFakeSpeaker([EN]);
    render(<ListenButton text="One. Two." hasSources={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Listen" }));
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(synth.cancelled).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Listen" })).toBeInTheDocument();
  });

  it("is hidden for Urdu answers on a device without an Urdu voice", () => {
    useFakeSpeaker([EN]);
    render(<ListenButton text="فیس کتنی ہے؟" hasSources={false} />);
    expect(screen.queryByRole("button", { name: "Listen" })).not.toBeInTheDocument();
  });

  it("is shown for Urdu answers when the device has an Urdu voice", () => {
    useFakeSpeaker([EN, UR]);
    render(<ListenButton text="فیس کتنی ہے؟" hasSources={false} />);
    expect(screen.getByRole("button", { name: "Listen" })).toBeInTheDocument();
  });
});
