/**
 * Web Speech play/pause — force standard American English voice.
 * Buttons: .speak-btn[data-speak="english text"]
 */
(function () {
  "use strict";

  const LABEL_PLAY = "播放";
  const LABEL_PAUSE = "暂停";
  const RATE = 0.92;
  const PITCH = 1;
  const STORAGE_KEY = "vocab-speak-voice-en-us";

  // Prefer natural / mainstream US English voices (macOS + Chrome + Edge)
  const PREFERRED_NAME_RE =
    /^(Samantha|Ava|Zoe|Allison|Nicky|Susan|Tom|Aaron|Google US English|Microsoft (Aria|Guy|Jenny|Michelle|Andrew|Emma) Offline|Microsoft (Aria|Guy|Jenny) Online|Samantha \(Enhanced\)|Ava \(Premium\))/i;

  const REJECT_NAME_RE =
    /Chinese|Zh[_-]|Taiwan|Hong Kong|Cantonese|Mandarin|Novelty|Bahh|Bells|Boing|Bubbles|Cellos|Good News|Bad News|Deranged|Hysterical|Pipe Organ|Trinoids|Whisper|Zarvox|Albert|Kathy|Princess|Junior|Superstar|Wobble|Eddy|Flo|Grandma|Grandpa|Reed|Rocko|Sandy|Shelley|Bruce|Fred|Junior|Organ|Trinoids|Zarvox|Google UK|en-GB|British|Australian|Indian|Irish|Scottish|South African|en-AU|en-IN|en-GB|en-IE|en-ZA|Daniel|Karen|Moira|Tessa|Rishi|Catherine|Serena/i;

  let activeBtn = null;
  let selectedVoiceURI = localStorage.getItem(STORAGE_KEY) || "";
  let voiceSelect = null;

  function resetBtn(btn) {
    if (!btn) return;
    btn.textContent = LABEL_PLAY;
    btn.setAttribute("aria-pressed", "false");
    btn.classList.remove("is-playing");
  }

  function resetAll() {
    document.querySelectorAll(".speak-btn.is-playing").forEach(resetBtn);
    activeBtn = null;
  }

  function stop() {
    window.speechSynthesis.cancel();
    resetAll();
  }

  function isUsEnglish(v) {
    const lang = (v.lang || "").replace("_", "-").toLowerCase();
    return lang === "en-us" || lang.startsWith("en-us");
  }

  function scoreVoice(v) {
    if (!isUsEnglish(v)) return -10000;
    const name = v.name || "";
    if (REJECT_NAME_RE.test(name)) return -5000;

    let score = 100;
    if (PREFERRED_NAME_RE.test(name)) score += 200;
    if (/Google US English/i.test(name)) score += 180;
    if (/Samantha/i.test(name)) score += 160;
    if (/Ava|Zoe|Allison/i.test(name)) score += 140;
    if (/Natural|Neural|Online|Premium|Enhanced|Quality/i.test(name)) score += 80;
    if (/Microsoft.*(Aria|Jenny|Guy)/i.test(name)) score += 120;
    // Prefer local high-quality system voices on macOS over compact
    if (v.localService) score += 40;
    if (/Compact/i.test(name)) score -= 80;
    // Slight preference for female clear classroom-style voices
    if (/Samantha|Ava|Zoe|Jenny|Aria|Allison|Susan|Nicky/i.test(name)) score += 20;
    return score;
  }

  function usVoices() {
    return window.speechSynthesis
      .getVoices()
      .filter((v) => isUsEnglish(v) && !REJECT_NAME_RE.test(v.name || ""))
      .sort((a, b) => scoreVoice(b) - scoreVoice(a));
  }

  function pickVoice() {
    const list = usVoices();
    if (!list.length) {
      // Fallback: any en-US even if name matched reject poorly
      const anyUs = window.speechSynthesis
        .getVoices()
        .filter(isUsEnglish)
        .sort((a, b) => scoreVoice(b) - scoreVoice(a));
      return anyUs[0] || null;
    }
    if (selectedVoiceURI) {
      const chosen = list.find((v) => v.voiceURI === selectedVoiceURI);
      if (chosen) return chosen;
    }
    return list[0];
  }

  function fillVoiceSelect() {
    if (!voiceSelect) return;
    const list = usVoices();
    const prev = selectedVoiceURI;
    voiceSelect.innerHTML = "";

    if (!list.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "未检测到美式英语语音（请到系统设置安装 English (US)）";
      voiceSelect.appendChild(opt);
      return;
    }

    list.forEach((v, i) => {
      const opt = document.createElement("option");
      opt.value = v.voiceURI;
      const tag = v.localService ? "本机" : "在线";
      opt.textContent = `${v.name} · ${v.lang}（${tag}）`;
      voiceSelect.appendChild(opt);
      if (i === 0 && !prev) selectedVoiceURI = v.voiceURI;
    });

    if (prev && list.some((v) => v.voiceURI === prev)) {
      voiceSelect.value = prev;
      selectedVoiceURI = prev;
    } else {
      voiceSelect.value = list[0].voiceURI;
      selectedVoiceURI = list[0].voiceURI;
      localStorage.setItem(STORAGE_KEY, selectedVoiceURI);
    }
  }

  function injectVoiceBar() {
    if (document.getElementById("voice-bar")) return;
    const host =
      document.querySelector(".page-head") ||
      document.querySelector(".wrap") ||
      document.body;

    const bar = document.createElement("div");
    bar.id = "voice-bar";
    bar.className = "voice-bar";
    bar.innerHTML =
      '<label for="voice-select">美式发音</label>' +
      '<select id="voice-select" aria-label="选择美式英语语音"></select>' +
      '<button type="button" id="voice-test" class="speak-btn voice-test">试听</button>' +
      '<span class="voice-tip muted">若仍怪异：系统设置 → 辅助功能 → 朗读内容 → 安装 English (US) 如 Samantha / Ava</span>';

    if (host.classList && host.classList.contains("page-head")) {
      host.insertAdjacentElement("afterend", bar);
    } else {
      host.insertAdjacentElement("afterbegin", bar);
    }

    voiceSelect = document.getElementById("voice-select");
    voiceSelect.addEventListener("change", function () {
      selectedVoiceURI = voiceSelect.value;
      localStorage.setItem(STORAGE_KEY, selectedVoiceURI);
      stop();
    });

    document.getElementById("voice-test").addEventListener("click", function (ev) {
      ev.preventDefault();
      const btn = ev.currentTarget;
      play("This is a standard American English pronunciation test.", btn);
    });

    fillVoiceSelect();
  }

  function play(text, btn) {
    if (!window.speechSynthesis) {
      alert("当前浏览器不支持语音朗读。请改用 Chrome / Safari / Edge。");
      return;
    }

    if (activeBtn === btn && (window.speechSynthesis.speaking || window.speechSynthesis.pending)) {
      stop();
      return;
    }

    stop();

    // Chrome: cancel can leave a stuck queue; resume/pause trick
    try {
      window.speechSynthesis.resume();
    } catch (_) {}

    const voice = pickVoice();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-US";
    u.rate = RATE;
    u.pitch = PITCH;
    u.volume = 1;
    if (voice) {
      u.voice = voice;
      u.lang = voice.lang || "en-US";
    }

    activeBtn = btn;
    btn.textContent = LABEL_PAUSE;
    btn.setAttribute("aria-pressed", "true");
    btn.classList.add("is-playing");

    u.onend = function () {
      if (activeBtn === btn) resetAll();
    };
    u.onerror = function () {
      if (activeBtn === btn) resetAll();
    };

    window.setTimeout(function () {
      window.speechSynthesis.speak(u);
    }, 40);
  }

  function onClick(ev) {
    const btn = ev.target.closest(".speak-btn");
    if (!btn || btn.id === "voice-test") return;
    const text = (btn.getAttribute("data-speak") || "").trim();
    if (!text) return;
    ev.preventDefault();
    play(text, btn);
  }

  function warmVoices() {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = function () {
      fillVoiceSelect();
    };
    // Some browsers populate asynchronously
    window.setTimeout(fillVoiceSelect, 100);
    window.setTimeout(fillVoiceSelect, 500);
  }

  document.addEventListener("DOMContentLoaded", function () {
    injectVoiceBar();
    warmVoices();
    document.body.addEventListener("click", onClick);
  });

  window.VocabSpeak = { play, stop, pickVoice, usVoices };
})();
