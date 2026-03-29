const API = "";

let globalDataset = [];
let tryOnState = { file: null, jewelryId: null, filter: null };
let styleState = { file: null, grams: 100 };

document.addEventListener("DOMContentLoaded", () => {
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

    // Submit
    const btn = document.getElementById("btn-tryon");
    btn.addEventListener("click", async () => {
        if (!tryOnState.file || !tryOnState.jewelryId) return;
        
        btn.disabled = true;
        btn.innerHTML = `Processing...`;
        document.getElementById("tryon-error").classList.add("hidden");
        
        const fd = new FormData();
        fd.append("image", tryOnState.file);
        fd.append("jewelry_id", tryOnState.jewelryId);

        try {
            const res = await fetch(`${API}/try-on`, { method: "POST", body: fd });
            const data = await res.json();
            
            if (!res.ok) throw new Error(data.detail || "Error");
            
            showResult("tryon", `${API}${data.result_image}`);
        } catch(err) {
            const errDiv = document.getElementById("tryon-error");
            errDiv.textContent = `⚠️ ${err.message}`;
            errDiv.classList.remove("hidden");
        } finally {
            btn.disabled = false;
            btn.innerHTML = `🪞 Try It On`;
        }
    });
}

function renderJewelryGrid() {
    const grid = document.getElementById("tryon-jewelry-grid");
    if (!grid) return;
    
    grid.innerHTML = "";
    const items = tryOnState.filter ? globalDataset.filter(i => i.type === tryOnState.filter) : globalDataset;
    
    items.forEach(item => {
        const card = document.createElement("div");
        card.className = `jewelry-card ${tryOnState.jewelryId === item.id ? 'selected' : ''}`;
        card.innerHTML = `
            <div class="jewelry-img-wrap">
                <img src="${API}/assets/${item.image}" alt="${item.name}">
            </div>
            <span class="jewelry-type">${item.type}</span>
            <span class="jewelry-name">${item.name}</span>
            <span class="jewelry-weight">${item.weight}g</span>
        `;
        card.addEventListener("click", () => {
            document.querySelectorAll(".jewelry-card").forEach(c => c.classList.remove("selected"));
            card.classList.add("selected");
            tryOnState.jewelryId = item.id;
            checkTryOnReady();
        });
        grid.appendChild(card);
    });
}

function checkTryOnReady() {
    document.getElementById("btn-tryon").disabled = !(tryOnState.file && tryOnState.jewelryId);
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
        
        presets.forEach(p => {
            if (parseInt(p.dataset.val) === val) p.classList.add("active");
            else p.classList.remove("active");
        });

        // Update distribution preview
        document.getElementById("dist-necklace").innerText = `${(val*0.4).toFixed(0)}g (40%)`;
        document.getElementById("dist-bangle").innerText = `${(val*0.35).toFixed(0)}g (35%)`;
        document.getElementById("dist-earring").innerText = `${(val*0.15).toFixed(0)}g (15%)`;
        document.getElementById("dist-ring").innerText = `${(val*0.10).toFixed(0)}g (10%)`;
    }

    slider.addEventListener("input", e => updateGrams(parseInt(e.target.value)));
    numInput.addEventListener("input", e => updateGrams(parseInt(e.target.value)));
    presets.forEach(p => p.addEventListener("click", e => updateGrams(parseInt(e.target.dataset.val))));

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
            list.innerHTML = data.selected_items.map(i => `
                <div class="item-row">
                    <span>${i.name}</span>
                    <span>${i.weight}g</span>
                </div>
            `).join("");
            document.getElementById("style-total-actual").innerText = `${data.total_weight_actual}g / ${data.total_weight_requested}g`;
            detailContainer.classList.remove("hidden");
            
        } catch(err) {
            const errDiv = document.getElementById("style-error");
            errDiv.textContent = `⚠️ ${err.message}`;
            errDiv.classList.remove("hidden");
        } finally {
            btn.disabled = false;
            btn.innerHTML = `⚖️ Generate Styled Look`;
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
