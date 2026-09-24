/* Search over the options a choice filter has already rendered.
 *
 * Only forms the server marked with data-admin-ext-choice-search get a box: the server
 * decides when a list is long enough. Nothing is fetched and nothing is submitted by this
 * script; it hides options that do not match and leaves the selection alone, so a checked
 * box that is filtered out of view is still sent. Without it, the form works as it is.
 *
 * The filter template links this file once per filter, so it may run several times on one
 * page; each form is enhanced once.
 */
(function () {
    "use strict";

    function normalise(text) {
        return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLocaleLowerCase().trim();
    }

    function enhance(form) {
        if (form.dataset.adminExtChoiceReady) {
            return;
        }
        form.dataset.adminExtChoiceReady = "true";

        const select = form.querySelector(".admin-ext-choice-select");
        const list = form.querySelector(".admin-ext-choice-options");
        const anchor = select || list;
        if (!anchor) {
            return;
        }
        // The first <option> is "All": always there, never searched.
        const items = select ? Array.from(select.options).slice(1) : Array.from(list.children);

        const search = document.createElement("input");
        search.type = "search";
        search.className = "admin-ext-choice-search";
        search.placeholder = form.dataset.adminExtChoiceSearch;
        search.setAttribute("aria-label", form.dataset.adminExtChoiceSearch);

        const nomatch = document.createElement("p");
        nomatch.className = "admin-ext-choice-nomatch";
        nomatch.textContent = form.dataset.adminExtChoiceNomatch;
        nomatch.style.display = "none";

        anchor.before(search);
        anchor.after(nomatch);

        search.addEventListener("input", function () {
            const needle = normalise(search.value);
            let shown = 0;
            for (const item of items) {
                const keep =
                    !needle ||
                    normalise(item.textContent).includes(needle) ||
                    (select !== null && item.selected);
                item.style.display = keep ? "" : "none";
                if (keep) {
                    shown += 1;
                }
            }
            nomatch.style.display = shown ? "none" : "";
        });
        // Enter searches; it does not submit a half-made selection.
        search.addEventListener("keydown", function (event) {
            if (event.key === "Enter") {
                event.preventDefault();
            }
        });
    }

    function init() {
        document.querySelectorAll("form.admin-ext-choice[data-admin-ext-choice-search]").forEach(enhance);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
