const API = "";

let globalDataset = [];
let tryOnState = { file: null, selectedIds: [], filter: null };
let styleState = { file: null, grams: 100 };

// Necklace length ordering for layering logic
const NECKLACE_LENGTH_ORDER = ["choker", "princess", "matinee", "opera", "rope"];
const NECKLACE_LENGTH_LABELS = {
    choker: "Choker (14-16\")",
    princess: "Princess (18\")",
    matinee: "Matinee (20-24\")",
    opera: "Opera (28-36\")",
    rope: "Rope (40\"+)"
};

document.addEventListener("DOMContentLoaded", () => {
    // Theme toggle
    const themeBtn = document.getElementById('theme-toggle');
    if (themeBtn) {
        const html = document.documentElement;
        const update = () => {
            const isLight = html.classList.contains('light');
            themeBtn.textContent = isLight ? '◑' : '◐';
            themeBtn.title = isLight ? 'Switch to dark mode' : 'Switch to light mode';
        };
        update();
        themeBtn.addEventListener('click', () => {
            html.classList.toggle('light');
            localStorage.setItem('ga-theme', html.classList.contains('light') ? 'light' : 'dark');
            update();
        });
    }

    // Navbar darkens on scroll
    const navbar = document.querySelector('.navbar');
    if (navbar) {
        window.addEventListener('scroll', () => {
            navbar.classList.toggle('scrolled', window.scrollY > 20);
        }, { passive: true });
    }

    // Scroll-reveal: adds .visible when element enters viewport
    const revealEls = document.querySelectorAll('[data-reveal]');
    if (revealEls.length) {
        const io = new IntersectionObserver((entries) => {
            entries.forEach(e => {
                if (e.isIntersecting) {
                    e.target.classList.add('visible');
                    io.unobserve(e.target);
                }
            });
        }, { threshold: 0.12 });
        revealEls.forEach(el => io.observe(el));
    }

    // 1. Load Dataset if on Try-On
    const grid = document.getElementById("tryon-jewelry-grid");
    if (grid) {
        fetch(`${API}/dataset`)
            .then(r => r.json())
            .then(data => {
                globalDataset = data;
                renderJewelryGrid();
            })
            .catch(err => {
                grid.innerHTML = `<div class="error-msg">Failed to load dataset: ${err}</div>`;
            });

        setupTryOnPage();
    }

    // 2. Setup Styling Page
    if (document.getElementById("style-dropzone")) {
        setupStylingPage();
    }
});

// --- Try-On Page Logic ---
function setupTryOnPage() {
    setupDropzone("tryon", file => {
        tryOnState.file = file;
        checkTryOnReady();
    });

    // Filters
    const tabs = document.querySelectorAll("#tryon-filters .tab");
    tabs.forEach(tab => {
        tab.addEventListener("click", (e) => {
            tabs.forEach(t => t.classList.remove("active"));
            e.target.classList.add("active");
            tryOnState.filter = e.target.dataset.filter === "all" ? null : e.target.dataset.filter;
            renderJewelryGrid();
        });
    });

    // Clear All button
    const clearAllBtn = document.getElementById("btn-clear-all");
    if (clearAllBtn) {
        clearAllBtn.addEventListener("click", () => {
            tryOnState.selectedIds = [];
            renderJewelryGrid();
            renderSelectedChips();
            fetchSuggestions();
            checkTryOnReady();
        });
    }

    // Submit — multi-item try-on 
    const btn = document.getElementById("btn-tryon");
    btn.addEventListener("click", async () => {
        if (!tryOnState.file || tryOnState.selectedIds.length === 0) return;

        btn.disabled = true;
        const count = tryOnState.selectedIds.length;
        btn.innerHTML = `Rendering ${count} piece${count > 1 ? 's' : ''}...`;
        document.getElementById("tryon-error").classList.add("hidden");

        // Show progress bar for multi-item
        const progressBar = document.getElementById("tryon-progress");
        const progressFill = document.getElementById("tryon-progress-fill");
        const progressText = document.getElementById("tryon-progress-text");

        if (count > 1) {
            progressBar.classList.remove("hidden");
            progressFill.style.width = "10%";
            progressText.textContent = `Applying ${count} jewelry items...`;
        }

        const fd = new FormData();
        fd.append("image", tryOnState.file);

        try {
            let res, data;

            if (count === 1) {
                // Single item — use original endpoint
                fd.append("jewelry_id", tryOnState.selectedIds[0]);
                res = await fetch(`${API}/try-on`, { method: "POST", body: fd });
            } else {
                // Multi item  
                fd.append("jewelry_ids", tryOnState.selectedIds.join(","));
                res = await fetch(`${API}/try-on-multi`, { method: "POST", body: fd });
            }

            // Animate progress
            if (count > 1) {
                progressFill.style.width = "80%";
                progressText.textContent = `Finalizing your look...`;
            }

            data = await res.json();

            if (!res.ok) throw new Error(data.detail || "Error");

            if (count > 1) {
                progressFill.style.width = "100%";
                progressText.textContent = `Done! Applied ${data.total_applied} of ${data.total_requested} items`;
            }

            showResult("tryon", `${API}${data.result_image}`);

            // Show applied items summary
            const appliedItems = data.applied_items || [data.jewelry_applied];
            showAppliedSummary(appliedItems);

        } catch (err) {
            const errDiv = document.getElementById("tryon-error");
            errDiv.textContent = `⚠️ ${err.message}`;
            errDiv.classList.remove("hidden");
        } finally {
            btn.disabled = false;
            btn.innerHTML = tryOnState.selectedIds.length > 0
                ? `Render ${tryOnState.selectedIds.length} Piece${tryOnState.selectedIds.length > 1 ? 's' : ''}`
                : `Render Ensemble`;

            // Hide progress after delay
            setTimeout(() => {
                progressBar.classList.add("hidden");
                progressFill.style.width = "0%";
            }, 2000);
        }
    });
}

function renderJewelryGrid() {
    const grid = document.getElementById("tryon-jewelry-grid");
    if (!grid) return;

    grid.innerHTML = "";
    let items = tryOnState.filter ? globalDataset.filter(i => i.type === tryOnState.filter) : globalDataset;

    items.forEach(item => {
        const isSelected = tryOnState.selectedIds.includes(item.id);
        const card = document.createElement("div");
        card.className = `jewelry-card ${isSelected ? 'selected' : ''}`;

        // Build length badge for necklaces
        let lengthBadge = "";
        if (item.type === "necklace" && item.length) {
            lengthBadge = `<span class="length-badge length-${item.length}">${item.length}</span>`;
        }

        card.innerHTML = `
            <div class="jewelry-img-wrap">
                <img src="${API}/assets/${item.image}" alt="${item.name}">
                ${isSelected ? '<div class="check-overlay">✓</div>' : ''}
            </div>
            ${lengthBadge}
            <span class="jewelry-type">${item.type}</span>
            <span class="jewelry-name">${item.name}</span>
            <span class="jewelry-weight">${item.weight}g</span>
        `;
        card.addEventListener("click", () => {
            toggleSelection(item.id);
        });
        grid.appendChild(card);
    });
}

function toggleSelection(itemId) {
    const idx = tryOnState.selectedIds.indexOf(itemId);
    if (idx > -1) {
        // Deselect
        tryOnState.selectedIds.splice(idx, 1);
    } else {
        // Select — check necklace length constraint
        const item = globalDataset.find(i => i.id === itemId);
        if (item && item.type === "necklace" && item.length) {
            // Check if there's already a necklace with the same length selected
            const sameLength = tryOnState.selectedIds.some(id => {
                const existing = globalDataset.find(i => i.id === id);
                return existing && existing.type === "necklace" && existing.length === item.length;
            });
            if (sameLength) {
                // Replace previously selected necklace of same length
                tryOnState.selectedIds = tryOnState.selectedIds.filter(id => {
                    const existing = globalDataset.find(i => i.id === id);
                    return !(existing && existing.type === "necklace" && existing.length === item.length);
                });
            }
        }
        tryOnState.selectedIds.push(itemId);
    }

    renderJewelryGrid();
    renderSelectedChips();
    fetchSuggestions();
    checkTryOnReady();
}

function renderSelectedChips() {
    const container = document.getElementById("selected-chips");
    const countEl = document.getElementById("selected-count");
    const clearAllBtn = document.getElementById("btn-clear-all");
    const count = tryOnState.selectedIds.length;

    countEl.textContent = `${count} selected`;

    if (count === 0) {
        container.innerHTML = '<div class="empty-chips">No pieces selected</div>';
        clearAllBtn.classList.add("hidden");
        return;
    }

    clearAllBtn.classList.remove("hidden");
    container.innerHTML = "";

    tryOnState.selectedIds.forEach(id => {
        const item = globalDataset.find(i => i.id === id);
        if (!item) return;

        const chip = document.createElement("div");
        chip.className = "chip";

        let lengthInfo = "";
        if (item.type === "necklace" && item.length) {
            lengthInfo = ` <span class="chip-length">${item.length}</span>`;
        }

        chip.innerHTML = `
            <img src="${API}/assets/${item.image}" alt="${item.name}" class="chip-img">
            <span class="chip-name">${item.name}${lengthInfo}</span>
            <span class="chip-weight">${item.weight}g</span>
            <button class="chip-remove" data-id="${item.id}">&times;</button>
        `;

        chip.querySelector(".chip-remove").addEventListener("click", (e) => {
            e.stopPropagation();
            toggleSelection(item.id);
        });

        container.appendChild(chip);
    });
}

function fetchSuggestions() {
    const section = document.getElementById("suggestions-section");
    const grid = document.getElementById("suggestions-grid");

    if (tryOnState.selectedIds.length === 0) {
        section.classList.add("hidden");
        return;
    }

    const selectedParam = tryOnState.selectedIds.join(",");

    fetch(`${API}/suggest-pairs?selected=${selectedParam}`)
        .then(r => r.json())
        .then(suggestions => {
            if (!suggestions || suggestions.length === 0) {
                section.classList.add("hidden");
                return;
            }

            section.classList.remove("hidden");
            grid.innerHTML = "";

            suggestions.forEach(item => {
                const isSelected = tryOnState.selectedIds.includes(item.id);
                const card = document.createElement("div");
                card.className = `suggestion-card ${isSelected ? 'selected' : ''}`;

                let lengthBadge = "";
                if (item.type === "necklace" && item.length) {
                    lengthBadge = `<span class="length-badge length-${item.length}">${item.length}</span>`;
                }

                card.innerHTML = `
                    <div class="suggestion-img-wrap">
                        <img src="${API}/assets/${item.image}" alt="${item.name}">
                    </div>
                    <div class="suggestion-info">
                        ${lengthBadge}
                        <span class="suggestion-name">${item.name}</span>
                        <span class="suggestion-reason">${item.reason}</span>
                    </div>
                    <button class="btn-add-suggestion">+ Add</button>
                `;

                card.querySelector(".btn-add-suggestion").addEventListener("click", (e) => {
                    e.stopPropagation();
                    toggleSelection(item.id);
                });

                grid.appendChild(card);
            });
        })
        .catch(() => {
            section.classList.add("hidden");
        });
}

function showAppliedSummary(items) {
    const container = document.getElementById("tryon-applied-summary");
    const list = document.getElementById("applied-items-list");

    if (!items || items.length === 0) {
        container.classList.add("hidden");
        return;
    }

    container.classList.remove("hidden");
    list.innerHTML = items.map(item => `
        <div class="applied-item">
            <img src="${API}/assets/${item.image}" alt="${item.name}" class="applied-item-img">
            <div class="applied-item-info">
                <span class="applied-item-name">${item.name}</span>
                <span class="applied-item-type">${item.type}${item.length ? ' · ' + item.length : ''} · ${item.weight}g</span>
            </div>
        </div>
    `).join("");
}

function checkTryOnReady() {
    const btn = document.getElementById("btn-tryon");
    const ready = tryOnState.file && tryOnState.selectedIds.length > 0;
    btn.disabled = !ready;

    const count = tryOnState.selectedIds.length;
    if (count > 0) {
        btn.innerHTML = `Render ${count} Piece${count > 1 ? 's' : ''}`;
    } else {
        btn.innerHTML = `Render Ensemble`;
    }
}

// --- Styling Page Logic ---
function setupStylingPage() {
    setupDropzone("style", file => {
        styleState.file = file;
        checkStyleReady();
    });

    // Grams Input sync
    const slider = document.getElementById("style-slider");
    const numInput = document.getElementById("style-number-input");
    const presets = document.querySelectorAll("#style-presets .preset");

    function updateGrams(val) {
        styleState.grams = val;
        slider.value = val;
        numInput.value = val;

        // Big weight display
        const weightDisplay = document.getElementById("weight-display");
        if (weightDisplay) weightDisplay.textContent = val;

        presets.forEach(p => {
            if (parseInt(p.dataset.val) === val) p.classList.add("active");
            else p.classList.remove("active");
        });

        // Update distribution values and bar widths
        const dist = {
            necklace: { frac: 0.40, pct: 40 },
            bangle:   { frac: 0.35, pct: 35 },
            earring:  { frac: 0.15, pct: 15 },
            ring:     { frac: 0.10, pct: 10 },
        };
        Object.entries(dist).forEach(([key, { frac, pct }]) => {
            const grams = (val * frac).toFixed(0);
            const valEl  = document.getElementById(`dist-${key}`);
            const barEl  = document.getElementById(`dist-bar-${key}`);
            if (valEl)  valEl.textContent = `${grams}g`;
            if (barEl)  barEl.style.width = `${pct}%`;
        });
    }

    slider.addEventListener("input", e => updateGrams(parseInt(e.target.value)));
    numInput.addEventListener("input", e => updateGrams(parseInt(e.target.value)));
    presets.forEach(p => p.addEventListener("click", e => updateGrams(parseInt(e.target.dataset.val))));
    updateGrams(styleState.grams); // initialise display on load

    // Submit
    const btn = document.getElementById("btn-generate");
    btn.addEventListener("click", async () => {
        if (!styleState.file) return;

        btn.disabled = true;
        btn.innerHTML = `Generating...`;
        document.getElementById("style-error").classList.add("hidden");
        document.getElementById("style-details").classList.add("hidden");

        const fd = new FormData();
        fd.append("image", styleState.file);
        fd.append("total_grams", styleState.grams);

        try {
            const res = await fetch(`${API}/generate-style`, { method: "POST", body: fd });
            const data = await res.json();

            if (!res.ok) throw new Error(data.detail || "Error");

            showResult("style", `${API}${data.result_image}`);

            // Show details
            const detailContainer = document.getElementById("style-details");
            const list = document.getElementById("style-items-list");
            list.innerHTML = data.selected_items.map(item => `
                <div class="applied-item">
                    <img src="${API}/assets/${item.image}" alt="${item.name}" class="applied-item-img">
                    <div class="applied-item-info">
                        <span class="applied-item-name">${item.name}</span>
                        <span class="applied-item-type">${item.type}${item.length ? ' · ' + item.length : ''} · ${item.weight}g</span>
                    </div>
                </div>
            `).join("");
            document.getElementById("style-total-actual").innerText = `${data.total_weight_actual}g / ${data.total_weight_requested}g`;
            detailContainer.classList.remove("hidden");

        } catch (err) {
            const errDiv = document.getElementById("style-error");
            errDiv.textContent = `⚠️ ${err.message}`;
            errDiv.classList.remove("hidden");
        } finally {
            btn.disabled = false;
            btn.innerHTML = `Generate Curation`;
        }
    });
}

function checkStyleReady() {
    document.getElementById("btn-generate").disabled = !styleState.file;
}

// --- Shared Logic ---
function setupDropzone(prefix, callback) {
    const dropzone = document.getElementById(`${prefix}-dropzone`);
    const input = document.getElementById(`${prefix}-file-input`);
    const preview = document.getElementById(`${prefix}-preview-img`);
    const placeholder = document.getElementById(`${prefix}-placeholder`);
    const clearBtn = document.getElementById(`${prefix}-clear-btn`);

    dropzone.addEventListener("click", () => input.click());

    dropzone.addEventListener("dragover", e => {
        e.preventDefault();
        dropzone.classList.add("active");
    });

    dropzone.addEventListener("dragleave", e => {
        e.preventDefault();
        dropzone.classList.remove("active");
    });

    dropzone.addEventListener("drop", e => {
        e.preventDefault();
        dropzone.classList.remove("active");
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            handleFile(e.dataTransfer.files[0]);
        }
    });

    input.addEventListener("change", e => {
        if (e.target.files && e.target.files[0]) {
            handleFile(e.target.files[0]);
        }
    });

    clearBtn.addEventListener("click", () => {
        input.value = "";
        preview.src = "";
        preview.classList.add("hidden");
        placeholder.classList.remove("hidden");
        clearBtn.classList.add("hidden");
        callback(null);
    });

    function handleFile(file) {
        if (!file.type.startsWith("image/")) return;
        const url = URL.createObjectURL(file);
        preview.src = url;
        preview.classList.remove("hidden");
        placeholder.classList.add("hidden");
        clearBtn.classList.remove("hidden");
        callback(file);
    }
}

function showResult(prefix, url) {
    const img = document.getElementById(`${prefix}-result-img`);
    const empty = document.getElementById(`${prefix}-empty-state`);
    const actions = document.getElementById(`${prefix}-result-actions`);

    img.src = url;
    img.classList.remove("hidden");
    empty.classList.add("hidden");
    actions.classList.remove("hidden");

    // Setup download
    const downBtn = document.getElementById(`btn-download-${prefix}`);
    downBtn.onclick = async () => {
        const res = await fetch(url);
        const blob = await res.blob();
        const objUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = objUrl;
        a.download = `goldaura_${prefix}_${Date.now()}.png`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    };
}
