/**
 * Urdu speech on devices without an Urdu voice (D18: browser only, no server cost).
 *
 * Chrome on Windows has no Urdu text-to-speech voice, but it has a Hindi one ("Google हिन्दी").
 * Spoken Hindi and Urdu are largely mutually intelligible, so an Urdu answer can be read by
 * the Hindi voice once its script is converted to Devanagari. Urdu script leaves out most short
 * vowels, so common words come from a dictionary and the rest from letter rules; the Hindi
 * voice's own schwa handling fills in the rest. Only the spoken audio uses this: the student
 * always sees the original Urdu text.
 */

// Frequent words in answers and questions, written as they are pronounced.
const WORDS: Record<string, string> = {
  "کی": "की", "کا": "का", "کے": "के", "کو": "को", "سے": "से", "میں": "में", "ہے": "है",
  "ہیں": "हैं", "ہو": "हो", "ہوں": "हूँ", "تھا": "था", "تھی": "थी", "تھے": "थे", "اور": "और",
  "یہ": "यह", "وہ": "वह", "یا": "या", "پر": "पर", "بھی": "भी", "نہیں": "नहीं", "کیا": "क्या",
  "کب": "कब", "کہاں": "कहाँ", "کیسے": "कैसे", "کون": "कौन", "کتنی": "कितनी", "کتنا": "कितना",
  "کتنے": "कितने", "لیے": "लिए", "لئے": "लिए", "ایک": "एक", "دو": "दो", "تین": "तीन", "اس": "इस",
  "ان": "इन", "آپ": "आप", "ہم": "हम", "مجھے": "मुझे", "آپکو": "आपको", "جی": "जी",
  "فیس": "फ़ीस", "داخلہ": "दाख़िला", "داخلے": "दाख़िले", "آخری": "आख़िरी",
  "تاریخ": "तारीख़", "دفتر": "दफ़्तर", "دفتری": "दफ़्तरी", "نمبر": "नंबर", "فون": "फ़ोन",
  "امتحان": "इम्तिहान", "امتحانی": "इम्तिहानी", "سمسٹر": "सेमेस्टर", "کریڈٹ": "क्रेडिट",
  "گھنٹہ": "घंटा", "گھنٹے": "घंटे", "روپے": "रुपये", "روپیہ": "रुपया", "یونیورسٹی": "यूनिवर्सिटी",
  "پروگرام": "प्रोग्राम", "پروگرامز": "प्रोग्राम्स", "معلومات": "मालूमात", "تصدیق": "तसदीक़",
  "ماخذ": "माख़ज़", "مطابق": "मुताबिक़", "براہ": "बराय", "کرم": "करम",
  "مہربانی": "मेहरबानी", "شکریہ": "शुक्रिया", "سلام": "सलाम", "السلام": "अस्सलाम", "علیکم": "अलैकुम",
  "ٹیوشن": "ट्यूशन", "اسکالرشپ": "स्कॉलरशिप", "ہاسٹل": "हॉस्टल", "کیمپس": "कैंपस", "مین": "मेन",
  "پیر": "पीर", "جمعہ": "जुमा", "ہفتہ": "हफ़्ता", "صبح": "सुबह", "شام": "शाम", "بجے": "बजे",
  "تک": "तक", "گزر": "गुज़र", "چکی": "चुकी", "چکا": "चुका", "رابطہ": "राब्ता", "کریں": "करें",
  "کر": "कर", "سکتے": "सकते", "سکتا": "सकता", "سکتی": "सकती", "چاہیے": "चाहिए", "چاہئیں": "चाहिएँ",
  "ٹیسٹ": "टेस्ट", "کمپیوٹر": "कंप्यूटर", "سائنس": "साइंस", "ریاضی": "रियाज़ी", "مضمون": "मज़मून",
  "طلبہ": "तलबा", "طالب": "तालिब", "علم": "इल्म", "پہلے": "पहले", "پہلی": "पहली", "دوسرے": "दूसरे",
  "ہر": "हर", "فی": "फ़ी", "کل": "कुल", "مزید": "मज़ीद", "تفصیلات": "तफ़सीलात", "متعلقہ": "मुताल्लिक़ा",
  // months and days (deadline answers)
  "جنوری": "जनवरी", "فروری": "फ़रवरी", "مارچ": "मार्च", "اپریل": "अप्रैल", "مئی": "मई",
  "جون": "जून", "جولائی": "जुलाई", "اگست": "अगस्त", "ستمبر": "सितंबर", "اکتوبر": "अक्टूबर",
  "نومبر": "नवंबर", "دسمبر": "दिसंबर", "منگل": "मंगल", "بدھ": "बुध", "جمعرات": "जुमेरात",
  "اتوار": "इतवार",
  // words seen in live answers
  "ویب": "वेब", "سائٹ": "साइट", "سٹرکچر": "स्ट्रक्चर", "صفحہ": "सफ़्हा", "صفحے": "सफ़्हे",
  "اعداد": "आदाद", "شمار": "शुमार", "شدہ": "शुदा", "دیگر": "दीगर", "تعلیم": "तालीम",
  "مطلوبہ": "मतलूबा", "اہلیت": "अहलियत", "ہدایات": "हिदायात", "درخواست": "दरख़्वास्त",
  "انٹری": "एंट्री", "انٹرمیڈیٹ": "इंटरमीडिएट", "فیصد": "फ़ीसद", "کم": "कम", "از": "अज़",
  "ادارہ": "इदारा", "پوچھیں": "पूछें", "ملیں": "मिलें", "ملے": "मिले", "ملتی": "मिलती",
  "خوش": "ख़ुश", "آمدید": "आमदीद", "اسلام": "इस्लाम", "پاکستان": "पाकिस्तान", "لاہور": "लाहौर",
  "ایڈمیشن": "एडमिशन", "صرف": "सिर्फ़", "ہوگا": "होगा", "ہوگی": "होगी", "شروع": "शुरू",
  "کلاسیں": "क्लासें", "کلاس": "क्लास", "سہولت": "सहूलत", "قسطوں": "क़िस्तों", "دی": "दी",
  "جا": "जा", "نمبرز": "नंबर्ज़", "پڑھی": "पढ़ी", "اگر": "अगर", "تو": "तो", "یونیورسٹیز": "यूनिवर्सिटीज़", "آفس": "ऑफ़िस", "سال": "साल", "مالی": "माली",
}

// Consonants. Letters with a nukta are written precomposed so the voice reads them correctly.
const CONSONANT: Record<string, string> = {
  "ب": "ब", "پ": "प", "ت": "त", "ٹ": "ट", "ث": "स", "ج": "ज", "چ": "च", "ح": "ह", "خ": "ख़",
  "د": "द", "ڈ": "ड", "ذ": "ज़", "ر": "र", "ڑ": "ड़", "ز": "ज़", "ژ": "झ़", "س": "स", "ش": "श",
  "ص": "स", "ض": "ज़", "ط": "त", "ظ": "ज़", "غ": "ग़", "ف": "फ़", "ق": "क़", "ک": "क", "گ": "ग",
  "ل": "ल", "م": "म", "ن": "न", "ہ": "ह", "ة": "ह",
};

// Aspirated pairs written with do-chashmi he (ھ).
const ASPIRATED: Record<string, string> = {
  "ب": "भ", "پ": "फ", "ت": "थ", "ٹ": "ठ", "ج": "झ", "چ": "छ", "د": "ध", "ڈ": "ढ", "ک": "ख",
  "گ": "घ", "ر": "रह", "ڑ": "ढ़", "ل": "ल्ह", "م": "म्ह", "ن": "न्ह",
};

const PUNCTUATION: Record<string, string> = { "۔": "।", "؟": "?", "،": ",", "؛": ";", "٪": "%" };
const URDU_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
const DIACRITICS = /[\u064B-\u065F\u0670\u06EA-\u06ED]/g; // zabar, zer, pesh, tashdeed ...

const VOWEL_MATRA: Record<string, string> = { "ا": "ा", "آ": "ा", "ی": "ी", "ے": "े", "و": "ो", "ع": "ा" };
const VOWEL_INITIAL: Record<string, string> = { "ا": "अ", "آ": "आ", "ع": "अ", "ی": "य", "و": "व", "ے": "ए", "ئ": "इ" };

/** One Urdu word to Devanagari: dictionary first, then letter rules. */
export function transliterateWord(word: string): string {
  const clean = word.replace(DIACRITICS, "").replace(/\u200C/g, "");
  const known = WORDS[clean];
  if (known) return known;
  const letters = [...clean];
  let out = "";
  let afterConsonant = false;
  for (let i = 0; i < letters.length; i += 1) {
    const ch = letters[i] ?? "";
    const next = letters[i + 1];
    const last = i === letters.length - 1;
    if (ch === "ھ") continue; // consumed with the previous consonant
    if (next === "ھ" && ASPIRATED[ch]) {
      out += ASPIRATED[ch];
      afterConsonant = true;
      continue;
    }
    if (ch === "ی" && next === "ں" && i === letters.length - 2 && afterConsonant) {
      out += "ें"; // final -یں of verbs and plurals: کریں -> करें, باتیں -> बातें
      i += 1;
      continue;
    }
    if (ch === "ں") {
      out += "ं";
      continue;
    }
    if (ch === "ہ" && last && afterConsonant) {
      out += "ा"; // final he after a consonant is a long a (داخلہ -> दाख़िला)
      continue;
    }
    const consonant = CONSONANT[ch];
    if (consonant) {
      out += consonant;
      afterConsonant = true;
      continue;
    }
    if (ch === "ئ") {
      out += next === "ے" || next === "ی" ? "" : "इ";
      afterConsonant = false;
      continue;
    }
    if ((ch === "ی" || ch === "ے") && letters[i - 1] === "ئ") {
      out += ch === "ی" ? "ई" : "ए"; // after the hamza seat ye is a full vowel: بھائی -> भाई
      afterConsonant = false;
      continue;
    }
    if (ch in VOWEL_MATRA) {
      if (i === 0) {
        // initial alef + ye or vao: ای -> ए, او -> ओ
        if (ch === "ا" && next === "ی") {
          out += "ए";
          i += 1;
        } else if (ch === "ا" && next === "و") {
          out += "ओ";
          i += 1;
        } else {
          out += VOWEL_INITIAL[ch] ?? "";
        }
        afterConsonant = ch === "ی" || ch === "و";
        continue;
      }
      if (afterConsonant) {
        if ((ch === "ی" || ch === "و") && next && (VOWEL_MATRA[next] || next === "ئ")) {
          out += ch === "ی" ? "य" : "व"; // ye / vao before a vowel are consonants
          afterConsonant = true;
        } else {
          out += VOWEL_MATRA[ch] ?? "";
          afterConsonant = false;
        }
      } else {
        out += ch === "ی" ? "य" : ch === "و" ? "व" : (VOWEL_INITIAL[ch] ?? "");
        afterConsonant = ch === "ی" || ch === "و";
      }
      continue;
    }
    out += ch;
    afterConsonant = false;
  }
  return out;
}

const URDU_WORD = /[\u0600-\u06FF\u200C]+/g;

/** Urdu text to Devanagari for a Hindi voice. Latin words, numbers and symbols stay. */
export function urduToDevanagari(text: string): string {
  return text
    .replace(/[۰-۹]/g, (d) => String(URDU_DIGITS.indexOf(d)))
    .replace(/[۔؟،؛٪]/g, (p) => PUNCTUATION[p] ?? p)
    .replace(URDU_WORD, (word) => transliterateWord(word));
}
