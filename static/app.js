(function cinemabotTheme() {
    const THEME_KEY = 'cinemabot-theme';

    function getStoredPreference() {
        try {
            return localStorage.getItem(THEME_KEY);
        } catch (e) {
            return null;
        }
    }

    function setStoredPreference(value) {
        try {
            localStorage.setItem(THEME_KEY, value);
        } catch (e) { /* private mode / blocked storage */ }
    }

    function resolveTheme() {
        const pref = getStoredPreference();
        if (pref === 'light') return 'light';
        if (pref === 'dark') return 'dark';
        return 'light';
    }

    function applyTheme() {
        const resolved = resolveTheme();
        const root = document.documentElement;
        root.dataset.theme = resolved;
        root.setAttribute('data-theme', resolved);

        const icon = document.getElementById('theme-toggle-icon');
        const btn = document.getElementById('theme-toggle');
        if (icon) {
            icon.className = '';
            icon.classList.add('fa-solid', resolved === 'light' ? 'fa-sun' : 'fa-moon', 'text-sm');
        }
        if (btn) {
            if (resolved === 'light') {
                btn.setAttribute('title', 'Switch to dark mode');
                btn.setAttribute('aria-label', 'Switch to dark mode');
            } else {
                btn.setAttribute('title', 'Switch to light mode');
                btn.setAttribute('aria-label', 'Switch to light mode');
            }
        }
    }

    function bindThemeToggle() {
        const btn = document.getElementById('theme-toggle');
        if (!btn || btn.dataset.themeBound === '1') return;
        btn.dataset.themeBound = '1';
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            const before = resolveTheme();
            const next = before === 'light' ? 'dark' : 'light';
            setStoredPreference(next);
            applyTheme();
        });
    }

    function initTheme() {
        applyTheme();
        bindThemeToggle();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTheme);
    } else {
        initTheme();
    }
})();

$(document).ready(function () {
    let ws = null;
    let conversationId = null;
    let isConnected = false;
    let currentAiBubble = null;
    let currentMessageId = null;
    let isStreaming = false;
    let stopRequested = false;

    const $chatMessages = $('#chat-messages');
    const $chatInput    = $('#chat-input');
    const $sendBtn      = $('#send-btn');
    const $stopBtn      = $('#stop-btn');
    const $newChatBtn   = $('#new-chat-btn');

    /* ─────────────────────────────────────────
       Markdown renderer
    ───────────────────────────────────────── */
    function formatMarkdown(text) {
        let html = text
            .replace(/### (.*?)(\n|$)/g, '<h3 class="markdown-h3">$1</h3>')
            .replace(/## (.*?)(\n|$)/g, '<h2 class="markdown-h2">$1</h2>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/^\s*[-•]\s+(.*?)$/gm, '<li>$1</li>');

        html = html.replace(/(<li>.*?<\/li>)+/gs, '<ul class="markdown-ul">$&</ul>');

        const blocks = html.split('\n\n');
        html = blocks.map(b => {
            if (/^<(h[23]|ul|li)/.test(b.trim())) return b;
            return `<p class="mb-2">${b.replace(/\n/g, '<br>')}</p>`;
        }).join('');

        return html;
    }

    /* ─────────────────────────────────────────
       WebSocket
    ───────────────────────────────────────── */
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${window.location.host}/api/v1/chat/ws`);

        ws.onopen  = () => { isConnected = true; };
        ws.onclose = () => {
            isConnected = false;
            document.body.classList.remove('agent-busy');
            setTimeout(connectWebSocket, 3000);
        };
        ws.onerror = (e) => console.error('WS error', e);
        ws.onmessage = (e) => handleWsMessage(JSON.parse(e.data));
    }

    /* ─────────────────────────────────────────
       Message handlers
    ───────────────────────────────────────── */
    function handleWsMessage(data) {
        if (stopRequested) return; // discard incoming after stop

        switch (data.type) {
            case 'info':
                conversationId = data.conversation_id;
                break;
            case 'message_id':
                currentMessageId = data.message_id;
                break;
            case 'status':
                updateStatus(data.content);
                break;
            case 'token':
                appendToken(data.content);
                break;
            case 'done':
                finishAiMessage();
                break;
            case 'error':
                showError(data.content);
                break;
        }
    }

    /* ─────────────────────────────────────────
       User message bubble
    ───────────────────────────────────────── */
    function appendUserMessage(message) {
        const html = `
        <div class="flex gap-3 justify-end msg-appear">
            <div class="user-bubble px-5 py-4 rounded-2xl rounded-tr-sm leading-relaxed max-w-[85%] text-sm">
                <p>${escapeHtml(message)}</p>
            </div>
            <div class="user-avatar w-8 h-8 rounded-lg flex items-center justify-center text-white shrink-0 mt-1">
                <i class="fa-solid fa-user text-xs"></i>
            </div>
        </div>`;
        $chatMessages.append(html);
        scrollToBottom();
    }

    /* ─────────────────────────────────────────
       AI bubble factory
    ───────────────────────────────────────── */
    function createAiBubble() {
        const id = 'ai-' + Date.now();
        const html = `
        <div class="flex gap-3 max-w-[88%] msg-appear" id="wrap-${id}">
            <div class="bot-avatar w-8 h-8 rounded-lg flex items-center justify-center text-white shrink-0 mt-1">
                <i class="fa-solid fa-robot text-xs"></i>
            </div>
            <div class="bot-bubble px-5 py-4 rounded-2xl rounded-tl-sm w-full">

                <!-- Status pill -->
                <div id="status-${id}" class="status-pill mb-3 hidden">
                    <div class="cinema-loader">
                        <div class="bar"></div><div class="bar"></div><div class="bar"></div>
                        <div class="bar"></div><div class="bar"></div>
                    </div>
                    <span class="status-text text-xs">Thinking…</span>
                </div>

                <!-- Shimmer placeholders (shown during first load) -->
                <div id="shimmer-${id}" class="space-y-2 mb-2">
                    <div class="shimmer w-3/4"></div>
                    <div class="shimmer w-full"></div>
                    <div class="shimmer w-5/6"></div>
                </div>

                <!-- Actual content -->
                <div id="body-${id}" class="markdown-body hidden"></div>

                <!-- Feedback bar (shown after done) -->
                <div id="fb-${id}" class="feedback-bar hidden">
                    <span class="feedback-label text-xs">Was this helpful?</span>
                    <button class="fb-btn like-btn" data-bubble="${id}" title="Thumbs up">
                        <i class="fa-solid fa-thumbs-up"></i>
                    </button>
                    <button class="fb-btn dislike-btn" data-bubble="${id}" title="Thumbs down">
                        <i class="fa-solid fa-thumbs-down"></i>
                    </button>
                </div>
            </div>
        </div>`;

        $chatMessages.append(html);
        scrollToBottom();

        currentAiBubble = {
            id,
            $wrap:      $(`#wrap-${id}`),
            $body:      $(`#body-${id}`),
            $status:    $(`#status-${id}`),
            $statusText:$(`#status-${id} .status-text`),
            $shimmer:   $(`#shimmer-${id}`),
            $fb:        $(`#fb-${id}`),
            rawText: '',
            messageId: null
        };
    }

    /* ─────────────────────────────────────────
       Status update
    ───────────────────────────────────────── */
    function updateStatus(text) {
        if (!currentAiBubble) createAiBubble();
        if (text) {
            currentAiBubble.$status.removeClass('hidden');
            currentAiBubble.$statusText.text(text);
        } else {
            currentAiBubble.$status.addClass('hidden');
        }
        scrollToBottom();
    }

    /* ─────────────────────────────────────────
       Token streaming
    ───────────────────────────────────────── */
    function appendToken(token) {
        if (!currentAiBubble) createAiBubble();

        // Hide shimmer + status on first real token
        if (currentAiBubble.$shimmer.is(':visible')) {
            currentAiBubble.$shimmer.hide();
            currentAiBubble.$body.removeClass('hidden');
        }
        currentAiBubble.$status.addClass('hidden');

        currentAiBubble.rawText += token;
        currentAiBubble.$body.html(formatMarkdown(currentAiBubble.rawText));
        scrollToBottom();
    }

    /* ─────────────────────────────────────────
       Finish / cleanup
    ───────────────────────────────────────── */
    function finishAiMessage() {
        document.body.classList.remove('agent-busy');
        isStreaming = false;
        stopRequested = false;
        $stopBtn.addClass('hidden');
        $sendBtn.removeClass('hidden');

        if (currentAiBubble) {
            currentAiBubble.$status.addClass('hidden');
            currentAiBubble.$shimmer.hide();

            // If stopped mid-stream, mark incomplete
            if (currentAiBubble.rawText === '') {
                currentAiBubble.$body.removeClass('hidden').html(
                    '<em class="text-stopped">Response stopped by user.</em>'
                );
            }

            // Attach stored message_id for feedback
            if (currentMessageId) {
                currentAiBubble.messageId = currentMessageId;
                currentAiBubble.$fb.attr('data-message-id', currentMessageId);
            }

            // Show feedback bar only if there's real content
            if (currentAiBubble.rawText) {
                currentAiBubble.$fb.removeClass('hidden');
            }

            currentAiBubble = null;
            currentMessageId = null;
        }

        $chatInput.prop('disabled', false).focus();
        $sendBtn.prop('disabled', false);
    }

    /* ─────────────────────────────────────────
       Error display
    ───────────────────────────────────────── */
    function showError(errorText) {
        if (!currentAiBubble) createAiBubble();
        currentAiBubble.$shimmer.hide();
        currentAiBubble.$status.addClass('hidden');
        currentAiBubble.$body.removeClass('hidden').html(
            `<span class="text-error text-sm"><i class="fa-solid fa-triangle-exclamation mr-1"></i>${escapeHtml(errorText)}</span>`
        );
        finishAiMessage();
    }

    /* ─────────────────────────────────────────
       Send message
    ───────────────────────────────────────── */
    function sendMessage() {
        const message = $chatInput.val().trim();
        if (!message || !isConnected || isStreaming) return;

        isStreaming = true;
        stopRequested = false;
        document.body.classList.add('agent-busy');

        $chatInput.val('').css('height', 'auto').prop('disabled', true);
        $sendBtn.prop('disabled', true).addClass('hidden');
        $stopBtn.removeClass('hidden');

        appendUserMessage(message);
        createAiBubble();
        updateStatus('Analyzing context…');

        ws.send(JSON.stringify({ message, conversation_id: conversationId }));
    }

    /* ─────────────────────────────────────────
       Stop button
    ───────────────────────────────────────── */
    $stopBtn.on('click', function () {
        stopRequested = true;
        finishAiMessage();
        // Close + reopen WS to cleanly abort server stream
        if (ws) ws.close();
    });

    /* ─────────────────────────────────────────
       Feedback (thumbs up / down)
    ───────────────────────────────────────── */
    $chatMessages.on('click', '.like-btn, .dislike-btn', function () {
        const $btn     = $(this);
        const bubbleId = $btn.data('bubble');
        const $fb      = $(`#fb-${bubbleId}`);
        const msgId    = $fb.attr('data-message-id');
        const isLike   = $btn.hasClass('like-btn');

        if (!msgId) {
            console.warn('No message_id attached to feedback bar — skipping API call.');
            return;
        }

        // Visual toggle immediately
        $fb.find('.fb-btn').removeClass('liked disliked');
        $btn.addClass(isLike ? 'liked' : 'disliked');

        // POST to backend
        $.ajax({
            url: `/api/v1/chat/message/${msgId}/feedback`,
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ is_liked: isLike }),
            error: function (err) {
                console.error('Feedback POST failed:', err);
                // Revert on failure
                $btn.removeClass('liked disliked');
            }
        });
    });

    /* ─────────────────────────────────────────
       Input / keyboard events
    ───────────────────────────────────────── */
    $chatInput.on('input', function () {
        this.style.height = 'auto';
        this.style.height = this.scrollHeight + 'px';
    });

    $chatInput.on('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!$sendBtn.prop('disabled') && !isStreaming) sendMessage();
        }
    });

    $sendBtn.on('click', function (e) {
        e.preventDefault();
        if (!$(this).prop('disabled') && !isStreaming) sendMessage();
    });

    /* ─────────────────────────────────────────
       New chat
    ───────────────────────────────────────── */
    $newChatBtn.on('click', function () {
        conversationId    = null;
        currentMessageId  = null;
        isStreaming       = false;
        stopRequested     = false;
        $stopBtn.addClass('hidden');
        $sendBtn.removeClass('hidden').prop('disabled', false);
        $chatInput.prop('disabled', false);

        document.body.classList.remove('agent-busy');
        $chatMessages.html(`
            <div class="flex gap-3 max-w-[88%] msg-appear">
                <div class="bot-avatar w-8 h-8 rounded-lg flex items-center justify-center text-white shrink-0 mt-1">
                    <i class="fa-solid fa-robot text-xs"></i>
                </div>
                <div class="bot-bubble px-5 py-4 rounded-2xl rounded-tl-sm">
                    <p class="welcome-text text-sm">New chat started! What movie are we exploring? 🍿</p>
                </div>
            </div>
        `);
        $chatInput.focus();
    });

    /* ─────────────────────────────────────────
       Scroll helpers
    ───────────────────────────────────────── */
    function scrollToBottom() {
        $chatMessages.scrollTop($chatMessages[0].scrollHeight);
    }

    $chatMessages.on('scroll', function () {
        const atBottom = this.scrollHeight - this.scrollTop - this.clientHeight < 80;
        $('#scroll-bottom-btn').toggleClass('hidden', atBottom);
    });

    $('#scroll-bottom-btn').on('click', scrollToBottom);

    /* ─────────────────────────────────────────
       Utils
    ───────────────────────────────────────── */
    function escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g,  '&amp;')
            .replace(/</g,  '&lt;')
            .replace(/>/g,  '&gt;')
            .replace(/"/g,  '&quot;')
            .replace(/'/g,  '&#039;');
    }

    /* ─────────────────────────────────────────
       Init
    ───────────────────────────────────────── */
    connectWebSocket();
    $chatInput.focus();
});
