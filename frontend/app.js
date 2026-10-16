/* =========================================================
   app.js — 校园知识库问答 前端交互逻辑
   改动对应卡片：
     CARD-3.1 多轮对话 UI（消息保留、气泡区分）
     CARD-3.2 错误处理（就地报错 + 重试，不弹 alert、不白屏）
     CARD-3.3 清空对话按钮
     CARD-3.4 加载动画（"思考中"三点，首字到达前可见）
     CARD-3.5 逐段注释（就你现在看到的这些）
     CARD-3.6 真·多轮：请求时把历史一起发给后端

   关于 CARD-3.6：
     后端 /chat/stream 现在接收 { question, history }。
     history 是"当前问题之前"的对话（role/content 数组），
     由后端拼成 [system, *history, 当前问题] 交给模型。
   ========================================================= */

/* ---------- 1. 拿到页面上需要用到的元素 ---------- */
const messagesEl = document.getElementById("messages");
const inputEl    = document.getElementById("question-input");
const sendBtn    = document.getElementById("send-btn");
const clearBtn   = document.getElementById("clear-btn");

/* ---------- 2. 全局状态 ---------- */
// history：内存中的对话记录，只增不改，是"这一轮聊了什么"的唯一凭证
// 每条形如 { role: "user" | "assistant", content: "..." }
const history = [];

// sessionId：会话编号。点"清空"时 +1，用来让还在飞的旧请求作废。
// 每个请求入场时记下当时的编号，往页面写之前先比对，不一致就闭嘴。
let sessionId = 0;

// busy：是否有请求正在进行。用来禁用发送，防止连点。
let busy = false;

/* ---------- 3. 小工具 ---------- */

// 把消息区滚到底部，保证最新一条始终可见
function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

// 创建一个"思考中"气泡里的三点动画元素（CARD-3.4）
function createThinkingEl() {
    const wrap = document.createElement("span");
    wrap.className = "thinking";
    wrap.textContent = "思考中";
    for (let i = 0; i < 3; i++) {
        const dot = document.createElement("span");
        dot.className = "dot";
        wrap.appendChild(dot);
    }
    return wrap;
}

/**
 * 往页面追加一条气泡，并返回这个元素，方便后续往里写字。
 * 只负责渲染，不碰 history（history 由调用方决定何时记）。
 */
function appendBubble(role, text = "") {
    const div = document.createElement("div");
    div.className = `message ${role}`;
    if (text) div.textContent = text;   // textContent 天然防 XSS，不用转义尖括号
    messagesEl.appendChild(div);
    scrollToBottom();
    return div;
}

/* ---------- 4. 初始状态：一条欢迎语（CARD-3.3 清空后也回到这里）---------- */
function showWelcome() {
    messagesEl.innerHTML = "";
    appendBubble(
        "assistant",
        "你好！我是校园信息助手 👋\n可以问我学校的事，比如「学校在哪个城市？」"
    );
}
showWelcome();

/* ---------- 5. 错误气泡 + 重试按钮（CARD-3.2）---------- */
/**
 * 把某个气泡就地改成"错误气泡"，并在下面挂一个重试按钮。
 * @param {HTMLElement} bubbleEl  原来那个助手气泡
 * @param {string} message        给用户看的错误提示
 * @param {string} question       出错的问题，重试时原样再发一次
 */
function renderError(bubbleEl, message, question) {
    bubbleEl.classList.remove("assistant");
    bubbleEl.classList.add("error");
    bubbleEl.textContent = "";

    const text = document.createElement("div");
    text.className = "error-text";
    text.textContent = "⚠️ " + message;
    bubbleEl.appendChild(text);

    const retryBtn = document.createElement("button");
    retryBtn.type = "button";
    retryBtn.className = "retry-btn";
    retryBtn.textContent = "重试";
    retryBtn.addEventListener("click", () => {
        // 重试前把这个错误气泡删掉，从干净的界面重来
        bubbleEl.remove();
        sendQuestion(question, { isRetry: true });
    });
    bubbleEl.appendChild(retryBtn);

    scrollToBottom();
}

/* ---------- 6. 发送问题（核心）---------- */
/**
 * @param {string}  questionOverride  直接指定问题（重试时用）；不传则读输入框
 * @param {object}  options           { isRetry: boolean }
 */
async function sendQuestion(questionOverride, options = {}) {
    const isRetry = options.isRetry === true;

    // 6.1 取问题：重试用传入的，正常发送读输入框
    const question = (questionOverride ?? inputEl.value).trim();
    if (!question) return;

    // 6.2 正在忙就忽略（双保险，正常情况下发送键已禁用）
    if (busy) return;

    // 6.3 重试收尾：上一轮失败时已把这条 user 压进了 history，
    //     这里先弹出来，下面 6.5 会原样再压回去，
    //     保证 history 里不会出现两条一模一样的提问（验收：断流重试不重复 user）
    if (isRetry && history.length > 0 && history[history.length - 1].role === "user") {
        history.pop();
    }

    // 6.4 ⭐ 拍历史快照（CARD-3.6 核心）
    //     刻意在"把当前问题压进 history"之前取，所以快照里
    //     只包含当前问题之前的对话；这份快照随请求发给后端。
    const historySnapshot = history.map((m) => ({ role: m.role, content: m.content }));

    // 6.5 把当前问题记入 history。
    //     正常发送是新增一条；重试是刚弹出又压回的同一句。
    history.push({ role: "user", content: question });

    // 6.6 渲染用户气泡：只有正常发送才加。
    //     重试时不重复渲染，避免界面上出现两条一样的问题。
    if (!isRetry) {
        inputEl.value = "";          // 正常发送才清空输入框
        appendBubble("user", question);
    }

    // 6.7 渲染助手气泡：先显示"思考中"三点，等第一个字到达再替换
    const bubbleEl = appendBubble("assistant");
    bubbleEl.appendChild(createThinkingEl());

    // 6.8 进入"忙碌"状态：禁用发送和输入
    busy = true;
    sendBtn.disabled = true;
    inputEl.disabled = true;

    // 6.9 记录本次请求属于哪个会话；若中途被"清空"打断，就作废
    const mySession = sessionId;

    // 助手最终文本；用 flag 区分"正常结束"和"中途断开"
    let answerText = "";
    let finished = false;   // 是否收到了后端明确的 [DONE]

    try {
        const resp = await fetch("/chat/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            // ⭐ 一起带上历史快照，后端据此拼多轮 messages
            body: JSON.stringify({ question, history: historySnapshot }),
        });

        // 6.10 HTTP 层错误（404 / 500 等）
        if (!resp.ok) {
            throw new Error(`服务器返回 HTTP ${resp.status}`);
        }

        // 6.11 读取流式响应体
        const reader = resp.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";
        let firstChunkReceived = false;

        while (true) {
            const { done, value } = await reader.read();

            // 6.12 流结束：跳出循环（是否正常由 finished 标记判断）
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // SSE 以空行分隔事件；最后一段可能不完整，留在 buffer 里
            const events = buffer.split("\n\n");
            buffer = events.pop() || "";

            for (const evt of events) {
                if (!evt.startsWith("data: ")) continue;
                const data = evt.slice(6);

                // 6.13 后端明确告知结束
                if (data === "[DONE]") {
                    finished = true;
                    break;
                }

                // 6.14 后端在生成过程中抛出的异常
                if (data.startsWith("[ERROR]")) {
                    throw new Error(data.slice(8).trim() || "服务端处理出错");
                }

                // 6.15 正常的一个文本分片：还原被转义的换行符
                const text = data.replace(/\\n/g, "\n");

                // 若期间用户点了"清空"，本次请求作废，直接停止写入
                if (mySession !== sessionId) return;

                // 6.16 第一个分片到达：把"思考中"换成真正的正文
                if (!firstChunkReceived) {
                    bubbleEl.textContent = "";
                    firstChunkReceived = true;
                }

                answerText += text;
                bubbleEl.textContent = answerText;
                scrollToBottom();
            }

            if (finished) break;
        }

        // 6.17 断流判定：循环结束却没收到 [DONE]，说明连接被中途掐断
        if (!finished) {
            throw new Error("连接中断，回答未完整返回");
        }

        // 6.18 成功：把这一轮的回答也记入历史，供下一轮当上下文
        if (mySession === sessionId) {
            history.push({ role: "assistant", content: answerText });
        }

    } catch (err) {
        // 6.19 任何异常都在"原地"报错，绝不 alert、不白屏
        if (mySession === sessionId) {
            // 网络层错误（断网等）拿到的是 TypeError，给一句人话
            const msg = (err instanceof TypeError)
                ? "网络连接失败，请检查网络后重试"
                : err.message;
            renderError(bubbleEl, msg, question);
        }
    } finally {
        // 6.20 无论成败，恢复可用状态
        busy = false;
        sendBtn.disabled = false;
        inputEl.disabled = false;
        inputEl.focus();
    }
}

/* ---------- 7. 清空对话（CARD-3.3）---------- */
function clearChat() {
    // 7.1 会话编号 +1：任何还在飞的请求都会因编号不匹配而停止写页面
    sessionId += 1;

    // 7.2 清掉内存里的历史，重新开始
    history.length = 0;

    // 7.3 解除忙碌态，免得清空后发送键还是灰的
    busy = false;
    sendBtn.disabled = false;
    inputEl.disabled = false;

    // 7.4 回到初始界面
    showWelcome();
    inputEl.focus();
}

/* ---------- 8. 事件绑定 ---------- */

// 点"发送"按钮
sendBtn.addEventListener("click", () => sendQuestion());

// 输入框里按回车发送
//   e.isComposing 判断是否在中文输入法选词状态，避免打字时误发
inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing) {
        sendQuestion();
    }
});

// 点"清空对话"按钮
clearBtn.addEventListener("click", clearChat);

// 页面加载后聚焦输入框，用户可以直接开始打字
inputEl.focus();
