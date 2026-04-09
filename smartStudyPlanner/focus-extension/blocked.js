const params = new URLSearchParams(window.location.search);
const domain = params.get("domain") || "This domain";
const reason = params.get("reason") || "domain-block";
const blockedUrl = params.get("url") || "";
const blockedTitle = params.get("title") || "";

document.getElementById("domainName").textContent = domain;

const detailText = document.getElementById("detailText");
if (detailText) {
  if (reason === "youtube-study") {
    detailText.textContent = "YouTube is allowed only for study-related content during Focus Mode. Try searching with study keywords, then continue your block.";
  } else {
    detailText.textContent = "Finish your current study block, then come back guilt-free when Focus Mode is off.";
  }
}

const allowOnceBtn = document.getElementById("allowOnceBtn");
if (allowOnceBtn && reason === "youtube-study" && blockedUrl) {
  allowOnceBtn.hidden = false;
  allowOnceBtn.addEventListener("click", () => {
    chrome.runtime.sendMessage(
      {
        type: "ALLOW_YOUTUBE_URL_ONCE",
        url: blockedUrl,
        title: blockedTitle
      },
      (response) => {
        if (response && response.ok) {
          window.location.replace(blockedUrl);
          return;
        }

        allowOnceBtn.disabled = true;
        allowOnceBtn.textContent = "Could not allow now";
      }
    );
  });
}

document.getElementById("closeTabBtn").addEventListener("click", () => {
  window.close();
});
