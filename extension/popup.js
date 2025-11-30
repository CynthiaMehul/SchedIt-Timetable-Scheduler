// Select page elements
const btn = document.getElementById("mainBtn");
const spinner = document.getElementById("spinner");
const statusBox = document.getElementById("status");

// Function to update status text
function showStatus(msg, color = "#444") {
  statusBox.style.color = color;
  statusBox.innerText = msg;
}

// Button click event
btn.addEventListener("click", async () => {

  showStatus("Reading page…");
  spinner.style.display = "block";

  // Get the active browser tab
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  // Inject code into the active tab to extract visible text
  chrome.scripting.executeScript({
    target: { tabId: tab.id },

    func: () => {

      // ---- Added Promise wrapper & delay ----
      return new Promise(resolve => {
        setTimeout(() => {

          function getCleanVisibleText(el) {
            const style = window.getComputedStyle(el);

            if (style.display === "none" || style.visibility === "hidden")
              return "";

            let result = "";

            for (const node of el.childNodes) {
              if (node.nodeType === Node.TEXT_NODE) {
                let t = node.textContent.replace(/\s+/g, " ").trim();
                if (t) result += t + " ";
              }
              else if (node.nodeType === Node.ELEMENT_NODE) {
                const tag = node.tagName.toLowerCase();
                const blockTags = ["div", "p", "br", "section", "article"];
                if (blockTags.includes(tag)) result += "\n";
                result += getCleanVisibleText(node);
                if (blockTags.includes(tag)) result += "\n";
              }
            }

            result = result.replace(
              /(\d{2}:\d{2} - \d{2}:\d{2})(?=\d{2}:\d{2} - \d{2}:\d{2})/g,
              "$1\n"
            );

            return result.replace(/\n{3,}/g, "\n\n").trim();
          }

          const full = getCleanVisibleText(document.body);

          const start = "Full Registration";
          const end = "Curriculum";
          const s = full.indexOf(start);
          const e = full.indexOf(end);

          if (s === -1 || e === -1 || e <= s) {
            resolve({
              raw: "Section not found",
              name: "Student"
            });
            return;
          }

          // STRONG NAME EXTRACTION
          let nameEl = document.querySelector(".user-name_detail");
          let studentName = "Student";

          if (nameEl) {
            studentName = nameEl.innerText.trim();
          } else {
            let match = document.body.innerText.match(/[A-Z][A-Z ]{3,40}/);
            studentName = match ? match[0].trim() : "Student";
          }

          resolve({
            raw: full.substring(s + start.length, e).trim(),
            name: studentName
          });

        }, 1200); // wait 1.2 sec for Angular to load
      });

    }

  }, async (res) => {

      // ---- Debug Log Added ----
      console.log("DEBUG: executeScript returned:", res);

      // If extraction failed
      if (!res || !res[0]) {
        spinner.style.display = "none";
        showStatus("Error extracting text.", "red");
        return;
      }

      const payload = res[0].result;

      // ---- Debug Log Added ----
      console.log("DEBUG: payload received:", payload);

      if (payload.raw === "Section not found") {
        spinner.style.display = "none";
        showStatus("Course section not found!", "red");
        return;
      }

      showStatus("Sending to website…");

      // Send extracted text to Django backend
      try {
        const response = await fetch("http://127.0.0.1:8000/api/upload_raw/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ raw_text: payload.raw, student_name: payload.name }),
          credentials: "include"
        });

        const data = await response.json();

        // If upload successful
        if (data.status === "ok") {
          showStatus("✔ Uploaded! Opening…", "green");
          spinner.style.display = "none";

          // Automatically open edit page
          chrome.tabs.create({
            url: "http://127.0.0.1:8000/edit/?new=1"
          });

        } else {
          spinner.style.display = "none";
          showStatus("Upload failed.", "red");
        }

      } catch (err) {
        spinner.style.display = "none";
        showStatus("Network error.", "red");
      }
    });
});
