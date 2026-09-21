/* Companion script for django_extensions_admin.jsonwidget.widgets.PrettyJSONWidget:
   auto-height, syntax highlighting, live validation and an explicit lossless reformat.
   No dependencies, no build step.

   The textarea keeps every native behaviour (undo, selection, form submit) and is only
   made transparent; a <pre> underneath holds the same text, coloured, kept in sync. */
(function () {
    "use strict";

    var DEBOUNCE_MS = 200;

    /* --- lossless formatting -------------------------------------------------
       Deliberately not JSON.parse + JSON.stringify: that rounds any integer past
       2^53, rewrites 1.0E2 as 100 and collapses duplicate keys. This scanner only
       rewrites the whitespace between tokens and copies every literal verbatim. */

    var NUMBER_RE = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/;
    var WHITESPACE = " \t\n\r";

    /* lenient: stop at the first character that is not JSON and return what was read
       so far, in one pass. Highlighting needs that for half-typed input; prettyText
       never uses it, so formatting still refuses anything it does not fully understand. */
    function tokenize(text, lenient) {
        var tokens = [];
        var i = 0;
        while (i < text.length) {
            var ch = text.charAt(i);
            if (WHITESPACE.indexOf(ch) !== -1) {
                i += 1;
                continue;
            }
            if (ch === '"') {
                var j = i + 1;
                var closed = false;
                while (j < text.length) {
                    var cur = text.charAt(j);
                    if (cur === "\\") {
                        j += 2;
                        continue;
                    }
                    if (cur === '"') {
                        closed = true;
                        j += 1;
                        break;
                    }
                    j += 1;
                }
                if (!closed) {
                    if (lenient) {
                        return tokens;
                    }
                    throw new Error("Unterminated string at " + i);
                }
                tokens.push({ kind: "string", start: i, end: j, text: text.slice(i, j) });
                i = j;
                continue;
            }
            if ("{}[],:".indexOf(ch) !== -1) {
                tokens.push({ kind: "punct", start: i, end: i + 1, text: ch });
                i += 1;
                continue;
            }
            var number = NUMBER_RE.exec(text.slice(i));
            if (number) {
                tokens.push({ kind: "number", start: i, end: i + number[0].length, text: number[0] });
                i += number[0].length;
                continue;
            }
            var rest = text.slice(i);
            var literal = ["true", "false", "null"].filter(function (word) {
                return rest.indexOf(word) === 0;
            })[0];
            if (literal) {
                tokens.push({ kind: "literal", start: i, end: i + literal.length, text: literal });
                i += literal.length;
                continue;
            }
            if (lenient) {
                return tokens;
            }
            throw new Error("Unexpected character " + ch + " at " + i);
        }
        return tokens;
    }

    function prettyText(text, indent) {
        var tokens = tokenize(text);
        var position = 0;
        var out = [];

        function take() {
            if (position >= tokens.length) {
                throw new Error("Unexpected end of JSON input");
            }
            position += 1;
            return tokens[position - 1];
        }

        function peek() {
            return position < tokens.length ? tokens[position] : null;
        }

        function pad(depth) {
            return new Array(indent * depth + 1).join(" ");
        }

        function container(depth, closing, item) {
            var opening = closing === "}" ? "{" : "[";
            var next = peek();
            if (next && next.kind === "punct" && next.text === closing) {
                take();
                out.push(opening + closing);
                return;
            }
            out.push(opening + "\n");
            for (;;) {
                out.push(pad(depth + 1));
                item(depth + 1);
                var sep = take();
                if (sep.kind !== "punct") {
                    throw new Error("Expected , or " + closing);
                }
                if (sep.text === ",") {
                    out.push(",\n");
                    continue;
                }
                if (sep.text === closing) {
                    out.push("\n" + pad(depth) + closing);
                    return;
                }
                throw new Error("Expected , or " + closing);
            }
        }

        function member(depth) {
            var key = take();
            if (key.kind !== "string") {
                throw new Error("Object keys must be strings");
            }
            out.push(key.text);
            var colon = take();
            if (colon.kind !== "punct" || colon.text !== ":") {
                throw new Error("Expected :");
            }
            out.push(": ");
            value(depth);
        }

        function value(depth) {
            var token = take();
            if (token.kind === "string" || token.kind === "number" || token.kind === "literal") {
                out.push(token.text);
                return;
            }
            if (token.text === "{") {
                container(depth, "}", member);
                return;
            }
            if (token.text === "[") {
                container(depth, "]", value);
                return;
            }
            throw new Error("Unexpected " + token.text);
        }

        if (!tokens.length) {
            throw new Error("Empty JSON input");
        }
        value(0);
        if (peek()) {
            throw new Error("Trailing data");
        }
        return out.join("");
    }

    /* --- highlighting -------------------------------------------------------- */

    function escapeHtml(text) {
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    var CLASS_FOR_KIND = {
        string: "admin-ext-json-string",
        number: "admin-ext-json-number",
        literal: "admin-ext-json-literal",
        punct: "admin-ext-json-punct"
    };

    /* Highlights as much as it can: broken input is still coloured up to the point the
       scanner gives up, and the remainder is shown as plain escaped text. */
    function highlight(text) {
        var tokens = tokenize(text, true);
        var html = "";
        var cursor = 0;
        for (var i = 0; i < tokens.length; i += 1) {
            var token = tokens[i];
            html += escapeHtml(text.slice(cursor, token.start));
            var next = tokens[i + 1];
            var isKey =
                token.kind === "string" && next && next.kind === "punct" && next.text === ":";
            var cls = isKey ? "admin-ext-json-key" : CLASS_FOR_KIND[token.kind];
            html += '<span class="' + cls + '">' + escapeHtml(token.text) + "</span>";
            cursor = token.end;
        }
        return html + escapeHtml(text.slice(cursor));
    }

    /* Character offset the parser choked on, or -1. V8 reports a position, Firefox a
       line/column pair, Safari neither - so this is best effort by design. */
    function errorOffset(text, message) {
        var offset = -1;
        var byPosition = /at position (\d+)/.exec(message);
        if (byPosition) {
            offset = Number(byPosition[1]);
        } else {
            var byLine = /line (\d+) column (\d+)/.exec(message);
            if (!byLine) {
                return -1;
            }
            var lines = text.split("\n");
            var lineIndex = Number(byLine[1]) - 1;
            if (lineIndex < 0 || lineIndex >= lines.length) {
                return -1;
            }
            offset = Number(byLine[2]) - 1;
            for (var i = 0; i < lineIndex; i += 1) {
                offset += lines[i].length + 1;
            }
        }
        if (offset >= text.length) {
            offset = text.length - 1;
        }
        // A newline has no width to underline; blame the last visible character.
        while (offset > 0 && text.charAt(offset) === "\n") {
            offset -= 1;
        }
        return offset;
    }

    /* --- the field ----------------------------------------------------------- */

    var MIRRORED_STYLES = [
        "fontFamily", "fontSize", "fontWeight", "fontStyle", "lineHeight", "letterSpacing",
        "textIndent", "tabSize", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
        "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth"
    ];

    function maxChars(textarea) {
        return Number(textarea.dataset.adminExtMaxChars || 100000);
    }

    function indentOf(textarea) {
        return Number(textarea.dataset.adminExtIndent || 2);
    }

    function paint(shell, textarea, offset) {
        if (!shell) {
            return;
        }
        var code = shell.querySelector("code");
        var text = textarea.value;
        if (text.length > maxChars(textarea)) {
            shell.classList.add("admin-ext-json-shell--plain");
            code.textContent = "";
            return;
        }
        try {
            if (offset < 0 || offset >= text.length) {
                code.innerHTML = highlight(text);
            } else {
                code.innerHTML =
                    highlight(text.slice(0, offset)) +
                    '<span class="admin-ext-json-mark">' +
                    escapeHtml(text.charAt(offset)) +
                    "</span>" +
                    highlight(text.slice(offset + 1));
            }
        } catch (error) {
            // A highlighting bug costs the colours, never the ability to read or edit.
            shell.classList.add("admin-ext-json-shell--plain");
            window.console.warn("admin-ext: highlighting disabled for this field", error);
            return;
        }
        shell.classList.remove("admin-ext-json-shell--plain");
    }

    function syncScroll(shell, textarea) {
        if (!shell) {
            return;
        }
        var pre = shell.querySelector("pre");
        pre.scrollTop = textarea.scrollTop;
        pre.scrollLeft = textarea.scrollLeft;
    }

    function syncMetrics(shell, textarea) {
        if (!shell) {
            return;
        }
        var pre = shell.querySelector("pre");
        var computed = window.getComputedStyle(textarea);
        MIRRORED_STYLES.forEach(function (property) {
            pre.style[property] = computed[property];
        });
    }

    function autosize(shell, textarea) {
        textarea.style.height = "auto";
        textarea.style.height = textarea.scrollHeight + 2 + "px";
        if (shell) {
            shell.style.height = textarea.offsetHeight + "px";
        }
    }

    function footerFor(shell, textarea) {
        var element = shell || textarea;
        // The field sits in an admin flex row; a footer left inside it would become
        // another flex item and line up beside the textarea instead of under it.
        var anchor = element.closest(".flex-container") || element;
        var node = anchor.nextElementSibling;
        if (!node || !node.classList.contains("admin-ext-json-footer")) {
            node = document.createElement("div");
            node.className = "admin-ext-json-footer";
            var error = document.createElement("p");
            error.className = "admin-ext-json-error";
            error.setAttribute("role", "status");
            var format = document.createElement("button");
            format.type = "button";
            format.className = "admin-ext-json-format";
            format.textContent = "Format";
            format.addEventListener("click", function () {
                reformat(shell, textarea);
            });
            node.appendChild(format);
            node.appendChild(error);
            anchor.insertAdjacentElement("afterend", node);
        }
        return node;
    }

    function validate(shell, textarea) {
        var footer = footerFor(shell, textarea);
        var error = footer.querySelector(".admin-ext-json-error");
        if (textarea.value.trim() === "") {
            textarea.classList.remove("admin-ext-json--invalid");
            textarea.removeAttribute("aria-invalid");
            error.textContent = "";
            paint(shell, textarea, -1);
            return false;
        }
        try {
            JSON.parse(textarea.value);
        } catch (parseError) {
            textarea.classList.add("admin-ext-json--invalid");
            textarea.setAttribute("aria-invalid", "true");
            error.textContent = parseError.message;
            paint(shell, textarea, errorOffset(textarea.value, parseError.message));
            return false;
        }
        textarea.classList.remove("admin-ext-json--invalid");
        textarea.removeAttribute("aria-invalid");
        error.textContent = "";
        paint(shell, textarea, -1);
        return true;
    }

    /* Replace the text through the edit history so ctrl/cmd-Z still undoes it. */
    function replaceValue(textarea, next) {
        var start = textarea.selectionStart;
        textarea.focus();
        textarea.setSelectionRange(0, textarea.value.length);
        var inserted = false;
        try {
            inserted = document.execCommand("insertText", false, next);
        } catch (error) {
            inserted = false;
        }
        if (!inserted || textarea.value !== next) {
            textarea.value = next;
        }
        var position = Math.min(start, textarea.value.length);
        textarea.setSelectionRange(position, position);
    }

    function reformat(shell, textarea) {
        if (textarea.value.length > maxChars(textarea)) {
            return;
        }
        var pretty;
        try {
            pretty = prettyText(textarea.value, indentOf(textarea));
        } catch (error) {
            validate(shell, textarea);
            return;
        }
        if (pretty !== textarea.value) {
            replaceValue(textarea, pretty);
            autosize(shell, textarea);
        }
        validate(shell, textarea);
    }

    /* The stylesheet hides the textarea's own text, so the overlay may only be built
       when that stylesheet is really there: a missing django_extensions_admin/json-widget.css would
       otherwise leave a field nobody can read. Everything else works without it. */
    function stylesheetLoaded() {
        var probe = window
            .getComputedStyle(document.documentElement)
            .getPropertyValue("--admin-ext-json-css");
        return probe.trim() === "1";
    }

    function shellFor(textarea) {
        var parent = textarea.parentElement;
        if (parent && parent.classList.contains("admin-ext-json-shell")) {
            return parent;
        }
        if (!stylesheetLoaded()) {
            return null;
        }
        var shell = document.createElement("div");
        shell.className = "admin-ext-json-shell";
        var pre = document.createElement("pre");
        pre.className = "admin-ext-json-layer";
        pre.setAttribute("aria-hidden", "true");
        pre.appendChild(document.createElement("code"));
        textarea.insertAdjacentElement("beforebegin", shell);
        shell.appendChild(pre);
        shell.appendChild(textarea);
        return shell;
    }

    function init(textarea) {
        // The inline empty-form template is cloned for every new row; initialising it
        // would stamp the ready flag onto the clones and leave them inert.
        if (textarea.dataset.adminExtReady === "1" || textarea.id.indexOf("__prefix__") !== -1) {
            return;
        }
        textarea.dataset.adminExtReady = "1";
        var shell = shellFor(textarea);
        syncMetrics(shell, textarea);
        autosize(shell, textarea);
        // Stored values can already be broken - say so before the field is touched.
        validate(shell, textarea);

        var timer = null;
        textarea.addEventListener("input", function () {
            autosize(shell, textarea);
            paint(shell, textarea, -1);
            syncScroll(shell, textarea);
            window.clearTimeout(timer);
            timer = window.setTimeout(function () {
                validate(shell, textarea);
            }, DEBOUNCE_MS);
        });
        textarea.addEventListener("scroll", function () {
            syncScroll(shell, textarea);
        });
        textarea.addEventListener("blur", function () {
            var valid = validate(shell, textarea);
            if (valid && textarea.dataset.adminExtBlurFormat === "1") {
                reformat(shell, textarea);
            }
        });
    }

    function initAll(root, reset) {
        var fields = root.querySelectorAll("textarea[data-admin-ext-json]");
        Array.prototype.forEach.call(fields, function (textarea) {
            if (reset) {
                delete textarea.dataset.adminExtReady;
            }
            init(textarea);
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        initAll(document, false);
    });

    // Rows added to an admin inline after page load.
    document.addEventListener("formset:added", function (event) {
        initAll(event.target, true);
    });

    window.adminExtJSON = { prettyText: prettyText, highlight: highlight, tokenize: tokenize };
})();
