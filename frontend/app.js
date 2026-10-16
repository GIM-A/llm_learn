const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("question-input");
const sendBtn = document.getElementById("send-btn");

// ========== 添加一条消息到界面 ==========
function addMessage(role, text = "") {
    const div = document.createElement("div");
    div.className = `message ${role}`;
    div.textContent = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
}

// ========== 发送问题 ==========
async function sendQuestion() {
    const question = inputEl.value.trim();
    if (!question) return;

    inputEl.value = "";
    sendBtn.disabled = true;
    inputEl.disabled = true;

    addMessage("user", question);

    // ⭐ 立刻显示占位
    const assistantEl = addMessage("assistant", "🔍 正在检索资料...");
    assistantEl.classList.add("loading");

    let firstChunkReceived = false;   // ⭐ 标记是否已收到第一块

    try {
        const resp = await fetch("/chat/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question }),
        });

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

        const reader = resp.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            let lines = buffer.split("\n\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
                if (!line.startsWith("data: ")) continue;
                const data = line.slice(6);

                if (data === "[DONE]") {
                    assistantEl.classList.remove("loading");
                    break;
                }

                if (data.startsWith("[ERROR]")) {
                    assistantEl.textContent = "⚠️ " + data.slice(8);
                    assistantEl.classList.remove("loading");
                    break;
                }

                const text = data.replace(/\\n/g, "\n");

                // ⭐ 第一次收到内容：清空占位
                if (!firstChunkReceived) {
                    assistantEl.textContent = "";
                    assistantEl.classList.remove("loading");
                    firstChunkReceived = true;
                }

                assistantEl.textContent += text;
                messagesEl.scrollTop = messagesEl.scrollHeight;
            }
        }
    } catch (err) {
        assistantEl.textContent = "⚠️ 请求失败：" + err.message;
        assistantEl.classList.remove("loading");
    } finally {
        sendBtn.disabled = false;
        inputEl.disabled = false;
        inputEl.focus();
    }
}
// ========== 绑定事件 ==========
sendBtn.addEventListener("click", sendQuestion);

inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing) {
        sendQuestion();
    }
});

// 页面加载后聚焦输入框
inputEl.focus();