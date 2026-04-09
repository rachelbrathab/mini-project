let emergencyTimerInterval = null;

function readState(callback) {
  chrome.storage.local.get(
    [
      "focusMode",
      "plannerProgressPercent",
      "plannerHasSchedule",
      "plannerActiveSubject",
      "plannerBlockedDomains",
      "plannerAllowedDomains",
      "plannerRewardActive",
      "plannerRewardRemainingSeconds",
      "emergencyUnlockUntil",
      "emergencyUnlockDate",
      "plannerHardMode",
      "plannerEmergencyRemaining",
      "youtubeLearnedKeywords"
    ],
    (state) => {
      const emergencyUnlockUntil = state.emergencyUnlockUntil || null;
      const emergencyUnlockActive = isFutureIsoDatetime(emergencyUnlockUntil);

    callback({
      focusMode: Boolean(state.focusMode),
      plannerProgressPercent: Number(state.plannerProgressPercent || 0),
      plannerHasSchedule: state.plannerHasSchedule !== false,
      plannerActiveSubject: state.plannerActiveSubject || "",
      plannerBlockedDomains: Array.isArray(state.plannerBlockedDomains) ? state.plannerBlockedDomains : [],
      plannerAllowedDomains: Array.isArray(state.plannerAllowedDomains) ? state.plannerAllowedDomains : [],
      plannerRewardActive: Boolean(state.plannerRewardActive),
      plannerRewardRemainingSeconds: Number(state.plannerRewardRemainingSeconds || 0),
      emergencyUnlockUntil,
      emergencyUnlockActive,
      plannerHardMode: Boolean(state.plannerHardMode),
      plannerEmergencyRemaining: Number(state.plannerEmergencyRemaining || 0),
      youtubeLearnedKeywords: state.youtubeLearnedKeywords && typeof state.youtubeLearnedKeywords === "object" ? state.youtubeLearnedKeywords : {}
    });
    }
  );
}

function writeState(nextState) {
  chrome.runtime.sendMessage(
    {
      type: "SET_FOCUS_MODE",
      focusMode: Boolean(nextState.focusMode)
    },
    () => {
      render();
    }
  );
}

function triggerEmergencyUnlock() {
  const hintText = document.getElementById("hintText");

  chrome.runtime.sendMessage({ type: "TRIGGER_EMERGENCY_UNLOCK" }, (response) => {
    if (chrome.runtime.lastError) {
      hintText.innerText = "Could not start emergency break. Reload extension and try again.";
      return;
    }

    if (!response || !response.ok) {
      if (response && response.reason === "hard-mode-limit") {
        hintText.innerText = "Hard mode active: no emergency breaks left for this session.";
        render();
        return;
      }

      hintText.innerText = "Emergency break could not be started. Try once more.";
      return;
    }

    hintText.innerText = "Emergency break started for 5 minutes.";
    render();
  });
}

function isFutureIsoDatetime(value) {
  if (!value) {
    return false;
  }

  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) && timestamp > Date.now();
}

function formatCountdown(totalSeconds) {
  const safeSeconds = Math.max(0, totalSeconds);
  const minutes = Math.floor(safeSeconds / 60);
  const seconds = safeSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function hideEmergencyTimer() {
  const emergencyTimer = document.getElementById("emergencyTimer");
  emergencyTimer.hidden = true;
  emergencyTimer.innerText = "";
}

function stopEmergencyTimer() {
  if (emergencyTimerInterval) {
    clearInterval(emergencyTimerInterval);
    emergencyTimerInterval = null;
  }
}

function startEmergencyTimer(untilIso) {
  const emergencyTimer = document.getElementById("emergencyTimer");
  const unlockTimestamp = Date.parse(untilIso || "");

  if (!Number.isFinite(unlockTimestamp)) {
    hideEmergencyTimer();
    stopEmergencyTimer();
    return;
  }

  const tick = () => {
    const remainingSeconds = Math.max(0, Math.floor((unlockTimestamp - Date.now()) / 1000));
    if (remainingSeconds <= 0) {
      hideEmergencyTimer();
      stopEmergencyTimer();
      render();
      return;
    }

    emergencyTimer.hidden = false;
    emergencyTimer.innerText = `Emergency break ends in ${formatCountdown(remainingSeconds)}`;
  };

  stopEmergencyTimer();
  tick();
  emergencyTimerInterval = setInterval(tick, 1000);
}

function getMotivationText(state) {
  if (!state.plannerHasSchedule) {
    return "No schedule yet. Create a quick plan and start strong.";
  }

  if (state.plannerProgressPercent >= 100) {
    return "All scheduled blocks are complete. Great work today.";
  }

  if (state.emergencyUnlockActive) {
    return "Emergency break is active. Recharge, then get right back to it.";
  }

  if (state.plannerRewardActive) {
    return "Nice work. Reward break unlocked after your last completed block.";
  }

  if (!state.focusMode) {
    return "Your goals are waiting. Start one focused session now.";
  }

  if (state.plannerAllowedDomains.includes("youtube.com")) {
    return "Great progress. Keep your momentum and finish strong.";
  }

  return "Stay locked in now, enjoy guilt-free later.";
}

function getRuleText(state) {
  if (!state.plannerHasSchedule) {
    return "No schedule generated yet";
  }

  if (state.emergencyUnlockActive) {
    return "Emergency access active for 5 minutes";
  }

  if (state.plannerHardMode && state.plannerEmergencyRemaining <= 0) {
    return "Hard mode active: emergency breaks exhausted";
  }

  if (state.plannerRewardActive) {
    const mins = Math.max(1, Math.ceil(state.plannerRewardRemainingSeconds / 60));
    return `Reward break active: ${mins} min unlocked`;
  }

  if (!state.focusMode) {
    return "All websites are currently allowed";
  }

  if (state.plannerBlockedDomains.length === 0) {
    return "Adaptive mode active: no domains blocked for this block";
  }

  if (state.plannerAllowedDomains.includes("youtube.com")) {
    return "YouTube unlocked, other listed sites blocked";
  }

  const hasYoutubeRule = state.plannerBlockedDomains.includes("youtube.com");

  if (hasYoutubeRule) {
    return "YouTube study-only mode on; other listed distractors blocked";
  }

  return `Blocking ${state.plannerBlockedDomains.join(", ")}`;
}

function getHintText(state) {
  if (!state.plannerHasSchedule) {
    return "Create a 25-min quick schedule in Smart Planner to enable Focus Mode.";
  }

  if (state.plannerActiveSubject) {
    const learnedCount = Object.keys(state.youtubeLearnedKeywords || {}).length;
    if (learnedCount > 0) {
      return `Adaptive rules tuned for: ${state.plannerActiveSubject} | Learned YouTube cues: ${learnedCount}`;
    }

    return `Adaptive rules tuned for: ${state.plannerActiveSubject}`;
  }

  return "Adaptive rules adjust automatically using your current study block.";
}

function render() {
  readState((state) => {
    const mantra = document.getElementById("mantraText");
    const modeStatus = document.getElementById("modeStatus");
    const ruleStatus = document.getElementById("ruleStatus");
    const hintText = document.getElementById("hintText");
    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");
    const emergencyBtn = document.getElementById("emergencyBtn");

    mantra.innerText = getMotivationText(state);
    mantra.classList.toggle("is-active", state.focusMode);

    modeStatus.innerText = state.focusMode ? "ON" : "OFF";
    modeStatus.classList.toggle("is-on", state.focusMode);

    ruleStatus.innerText = getRuleText(state);
    hintText.innerText = getHintText(state);

    if (state.emergencyUnlockActive && state.emergencyUnlockUntil) {
      startEmergencyTimer(state.emergencyUnlockUntil);
    } else {
      hideEmergencyTimer();
      stopEmergencyTimer();
    }

    startBtn.disabled = state.focusMode || !state.plannerHasSchedule || state.emergencyUnlockActive;
    stopBtn.disabled = !state.focusMode;
    emergencyBtn.disabled = state.plannerHardMode && state.plannerEmergencyRemaining <= 0;
  });
}

document.getElementById("startBtn").addEventListener("click", () => {
  writeState({ focusMode: true });
});

document.getElementById("stopBtn").addEventListener("click", () => {
  writeState({ focusMode: false });
});

document.getElementById("emergencyBtn").addEventListener("click", () => {
  triggerEmergencyUnlock();
});

chrome.storage.onChanged.addListener(render);
render();
