/* Companion script for django_extensions_admin.jsonwidget.widgets.PrettyJSONWidget:
   auto-height, syntax highlighting, live validation and an explicit lossless reformat.
   No dependencies, no build step.

   The textarea keeps every native behaviour (undo, selection, form submit) and is only
   made transparent; a <pre> underneath holds the same text, coloured, kept in sync. */
(function () {
    "use strict";

    var DEBOUNCE_MS = 200;
    var WHITESPACE = " \t\n\r";

    /* --- highlighting --------------------------------------------------------
       One pass: a string followed by a colon is a key, then plain strings, numbers,
       literals and punctuation. Anything unmatched - whitespace, half-typed input -
       stays plain, so broken text is still readable. The server mirrors this regex in
       jsonwidget/readonly.py. */

    var TOKEN_RE = /("(?:\\.|[^"\\])*")(\s*:)|("(?:\\.|[^"\\])*")|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b|([{}[\],:])/g;

    var CLASS_FOR_GROUP = [
        null,
        "admin-ext-json-key",
        "admin-ext-json-punct",
        "admin-ext-json-string",
        "admin-ext-json-number",
        "admin-ext-json-literal",
        "admin-ext-json-punct"
    ];

    function escapeHtml(text) {
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    function highlight(text) {
        var html = "";
        var last = 0;
        var match;
        TOKEN_RE.lastIndex = 0;
        while ((match = TOKEN_RE.exec(text)) !== null) {
            html += escapeHtml(text.slice(last, match.index));
            for (var group = 1; group < CLASS_FOR_GROUP.length; group += 1) {
                if (match[group] !== undefined) {
                    html +=
                        '<span class="' + CLASS_FOR_GROUP[group] + '">' +
                        escapeHtml(match[group]) +
                        "</span>";
                }
            }
            last = match.index + match[0].length;
        }
        return html + escapeHtml(text.slice(last));
    }

    /* --- lossless re-indenting ------------------------------------------------
       Deliberately not JSON.parse + JSON.stringify: that rounds any integer past 2^53,
       rewrites 1.0E2 as 100 and collapses duplicate keys - in text the user just typed
       and has not sent anywhere yet. This rewrites only the whitespace between
       structural characters and copies every literal through byte for byte.

       It carries no grammar of its own: reformat() runs it only on text JSON.parse has
       already accepted, so the native parser owns validity and this owns fidelity. */

    function pad(indent, depth) {
        return new Array(indent * depth + 1).join(" ");
    }

    function skipWhitespace(text, index) {
        while (index < text.length && WHITESPACE.indexOf(text.charAt(index)) !== -1) {
            index += 1;
        }
        return index;
    }

    function endOfString(text, start) {
        var index = start + 1;
        while (index < text.length) {
            var ch = text.charAt(index);
            if (ch === "\\") {
                index += 2;
                continue;
            }
            index += 1;
            if (ch === '"') {
                return index;
            }
        }
        return index;
    }

    function reindent(text, indent) {
        var out = "";
        var depth = 0;
        var i = 0;
        while (i < text.length) {
            var ch = text.charAt(i);
            if (ch === '"') {
                var end = endOfString(text, i);
                out += text.slice(i, end);
                i = end;
                continue;
            }
            if (WHITESPACE.indexOf(ch) !== -1) {
                i += 1;
                continue;
            }
            if (ch === "{" || ch === "[") {
                var after = skipWhitespace(text, i + 1);
                var closing = ch === "{" ? "}" : "]";
                if (text.charAt(after) === closing) {
                    // An empty container keeps its place on the line.
                    out += ch + closing;
                    i = after + 1;
                    continue;
                }
                depth += 1;
                out += ch + "\n" + pad(indent, depth);
                i += 1;
                continue;
            }
            if (ch === "}" || ch === "]") {
                depth -= 1;
                out += "\n" + pad(indent, depth) + ch;
                i += 1;
                continue;
            }
            if (ch === ",") {
                out += ",\n" + pad(indent, depth);
                i += 1;
                continue;
            }
            if (ch === ":") {
                out += ": ";
                i += 1;
                continue;
            }
            // A number or a literal: copied verbatim, which is the whole point.
            out += ch;
            i += 1;
        }
        return out;
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
        return Number(textarea.dataset.adminExtMaxChars || 200000);
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
        // Validity first, from the native parser; only then the whitespace-only rewrite.
        if (!validate(shell, textarea)) {
            return;
        }
        var pretty = reindent(textarea.value, indentOf(textarea));
        if (pretty !== textarea.value) {
            replaceValue(textarea, pretty);
            autosize(shell, textarea);
            paint(shell, textarea, -1);
        }
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
            if (textarea.dataset.adminExtBlurFormat === "1") {
                reformat(shell, textarea);
            } else {
                validate(shell, textarea);
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
})();
