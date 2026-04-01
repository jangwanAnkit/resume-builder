/* -----------------------------------------------------------
   Resume Customizer — app.js
   Tab switching, dynamic arrays, form serialization,
   pdf.js preview, API calls for generate & save.
   ----------------------------------------------------------- */

// ---------------------------------------------------------------------------
// State — hydrated from server-rendered window.__DATA__
// ---------------------------------------------------------------------------
const state = JSON.parse(JSON.stringify(window.__DATA__));

// Staged review state for AI tailoring
let originalSnapshot = null;   // pre-tailoring state for Reset
let pendingTailored = null;    // AI results awaiting user approval
let currentPreviewTab = "pdf"; // "pdf" or "ai"
let lastAiResultsHTML = "";    // persisted AI results HTML

// PDF preview state
let pdfBlob = null;
let pdfDoc = null;
let currentPage = 1;
let totalPages = 0;

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    populateScalarFields();
    renderEducation();
    renderExperience();
    renderProjects();
    initTabs();
    initAITailoring();
});

// ---------------------------------------------------------------------------
// Tabs & AI Config
// ---------------------------------------------------------------------------
function initTabs() {
    const btns = document.querySelectorAll("#sidebar button");
    btns.forEach((btn) => {
        btn.addEventListener("click", () => {
            btns.forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            document.querySelectorAll(".section").forEach((s) => s.classList.remove("active"));
            document.getElementById("section-" + btn.dataset.tab).classList.add("active");
        });
    });
}

function switchPreviewTab(tab) {
    currentPreviewTab = tab;
    const tabPdf = document.getElementById("tab-pdf");
    const tabAi = document.getElementById("tab-ai");
    const pageNav = document.getElementById("page-nav");

    if (tab === "pdf") {
        tabPdf.classList.add("active");
        tabAi.classList.remove("active");
        if (pdfBlob) {
            renderPDFPreview(pdfBlob);
        } else {
            const body = document.getElementById("preview-body");
            body.innerHTML = `<div class="preview-empty" id="preview-empty">CLICK GENERATE TO PREVIEW</div>`;
            if (pageNav) pageNav.style.display = "none";
        }
    } else {
        tabPdf.classList.remove("active");
        tabAi.classList.add("active");
        if (pageNav) pageNav.style.display = "none";
        const body = document.getElementById("preview-body");
        body.innerHTML = lastAiResultsHTML;
    }
}

function showPreviewTabs() {
    const tabsBar = document.getElementById("preview-tabs");
    if (tabsBar) tabsBar.style.display = "flex";
}

function initAITailoring() {
    const providerSelect = document.getElementById("ai-provider");
    if (!providerSelect) return;

    const PROVIDER_CONFIGS = {
        "openai": { base_url: "", model: "gpt-4o-mini" },
        "cerebras": { base_url: "https://api.cerebras.ai/v1", model: "llama3.1-8b" },
        "nvidia": { base_url: "https://integrate.api.nvidia.com/v1", model: "moonshotai/kimi-k2.5" },
        "gemini": { base_url: "https://generativelanguage.googleapis.com/v1beta/openai/", model: "gemini-2.5-flash" },
        "openrouter": { base_url: "https://openrouter.ai/api/v1", model: "openrouter/free" },
        "openrouter_meta": { base_url: "https://openrouter.ai/api/v1", model: "meta-llama/llama-3.3-70b-instruct:free" },
        "custom": { base_url: "", model: "" }
    };

    providerSelect.addEventListener("change", (e) => {
        const config = PROVIDER_CONFIGS[e.target.value];
        if (config) {
            document.getElementById("ai-model").value = config.model;
            document.getElementById("ai-base-url").value = config.base_url;
        }
    });
}

// ---------------------------------------------------------------------------
// Scalar fields — Profile & Contact (data-path driven)
// ---------------------------------------------------------------------------
function populateScalarFields() {
    document.querySelectorAll("[data-path]").forEach((el) => {
        const val = getNestedValue(state, el.dataset.path);
        if (val !== undefined && val !== null) {
            el.value = val;
        }
        el.addEventListener("input", () => {
            setNestedValue(state, el.dataset.path, el.value);
        });
    });
}

function getNestedValue(obj, path) {
    return path.split(".").reduce((o, k) => (o && o[k] !== undefined ? o[k] : undefined), obj);
}

function setNestedValue(obj, path, value) {
    const keys = path.split(".");
    let cur = obj;
    for (let i = 0; i < keys.length - 1; i++) {
        if (cur[keys[i]] === undefined) cur[keys[i]] = {};
        cur = cur[keys[i]];
    }
    cur[keys[keys.length - 1]] = value;
}

// ---------------------------------------------------------------------------
// Education
// ---------------------------------------------------------------------------
function renderEducation() {
    const list = document.getElementById("education-list");
    list.innerHTML = "";
    const edu = state.education || (state.education = { education: [] });
    const items = edu.education || (edu.education = []);

    items.forEach((entry, i) => {
        list.appendChild(createEducationEntry(entry, i));
    });
}

function createEducationEntry(entry, index) {
    const div = document.createElement("div");
    div.className = "array-entry";
    div.innerHTML = `
        <div class="array-entry-header">
            <span class="array-entry-number">#${index + 1}</span>
            <button type="button" class="btn-danger btn-small" onclick="removeEducation(${index})">REMOVE</button>
        </div>
        <div class="field-row">
            <div class="field">
                <label>INSTITUTION</label>
                <input type="text" value="${esc(entry.institution || "")}" data-edu="${index}" data-key="institution">
            </div>
            <div class="field">
                <label>LOCATION</label>
                <input type="text" value="${esc(entry.location || "")}" data-edu="${index}" data-key="location">
            </div>
        </div>
        <div class="field">
            <label>DEGREE</label>
            <input type="text" value="${esc(entry.degree || "")}" data-edu="${index}" data-key="degree">
        </div>
        <div class="field">
            <label>DURATION</label>
            <input type="text" value="${esc(entry.duration || "")}" data-edu="${index}" data-key="duration">
        </div>
    `;
    div.querySelectorAll("input").forEach((inp) => {
        inp.addEventListener("input", () => {
            const idx = parseInt(inp.dataset.edu);
            state.education.education[idx][inp.dataset.key] = inp.value;
        });
    });
    return div;
}

function addEducation() {
    if (!state.education) state.education = { education: [] };
    if (!state.education.education) state.education.education = [];
    state.education.education.push({ institution: "", location: "", degree: "", duration: "" });
    renderEducation();
}

function removeEducation(index) {
    state.education.education.splice(index, 1);
    renderEducation();
}

// ---------------------------------------------------------------------------
// Experience
// ---------------------------------------------------------------------------
function renderExperience() {
    const list = document.getElementById("experience-list");
    list.innerHTML = "";
    const exp = state.experience || (state.experience = { experience: [] });
    const items = exp.experience || (exp.experience = []);

    items.forEach((entry, i) => {
        list.appendChild(createExperienceEntry(entry, i));
    });
}

function createExperienceEntry(entry, index) {
    const div = document.createElement("div");
    div.className = "array-entry";

    const details = entry.details || [];
    const detailsHtml = details
        .map(
            (d, di) => `
        <div class="detail-item">
            <textarea data-exp="${index}" data-detail="${di}">${esc(d)}</textarea>
            <button type="button" class="btn-danger btn-small" onclick="removeDetail(${index}, ${di})">×</button>
        </div>`
        )
        .join("");

    div.innerHTML = `
        <div class="array-entry-header">
            <span class="array-entry-number">#${index + 1}</span>
            <button type="button" class="btn-danger btn-small" onclick="removeExperience(${index})">REMOVE</button>
        </div>
        <div class="field-row">
            <div class="field">
                <label>COMPANY</label>
                <input type="text" value="${esc(entry.company || "")}" data-exp-field="${index}" data-key="company">
            </div>
            <div class="field">
                <label>ROLE</label>
                <input type="text" value="${esc(entry.role || "")}" data-exp-field="${index}" data-key="role">
            </div>
        </div>
        <div class="field-row">
            <div class="field">
                <label>START DATE</label>
                <input type="text" value="${esc(entry.startDate || "")}" data-exp-field="${index}" data-key="startDate" placeholder="YYYY-MM">
            </div>
            <div class="field">
                <label>END DATE</label>
                <input type="text" value="${esc(entry.endDate || "")}" data-exp-field="${index}" data-key="endDate" placeholder="YYYY-MM OR EMPTY">
            </div>
        </div>
        <div class="field">
            <label>LOCATION</label>
            <input type="text" value="${esc(entry.location || "")}" data-exp-field="${index}" data-key="location">
        </div>
        <div class="field-group">
            <div class="field-group-title">DETAIL BULLETS</div>
            <div id="details-${index}">${detailsHtml}</div>
            <button type="button" class="btn-secondary btn-small" onclick="addDetail(${index})">+ ADD BULLET</button>
        </div>
    `;

    div.querySelectorAll("[data-exp-field]").forEach((inp) => {
        inp.addEventListener("input", () => {
            const idx = parseInt(inp.dataset.expField);
            const key = inp.dataset.key;
            const val = inp.value;
            state.experience.experience[idx][key] = val === "" && key === "endDate" ? null : val;
        });
    });

    div.querySelectorAll("[data-detail]").forEach((ta) => {
        ta.addEventListener("input", () => {
            const ei = parseInt(ta.dataset.exp);
            const di = parseInt(ta.dataset.detail);
            state.experience.experience[ei].details[di] = ta.value;
        });
    });

    return div;
}

function addExperience() {
    if (!state.experience) state.experience = { experience: [] };
    if (!state.experience.experience) state.experience.experience = [];
    state.experience.experience.push({
        company: "",
        role: "",
        startDate: "",
        endDate: null,
        location: "",
        details: [],
    });
    renderExperience();
}

function removeExperience(index) {
    state.experience.experience.splice(index, 1);
    renderExperience();
}

function addDetail(expIndex) {
    state.experience.experience[expIndex].details.push("");
    renderExperience();
}

function removeDetail(expIndex, detailIndex) {
    state.experience.experience[expIndex].details.splice(detailIndex, 1);
    renderExperience();
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------
function renderProjects() {
    const list = document.getElementById("projects-list");
    list.innerHTML = "";
    const proj = state.projects || (state.projects = { projects: [] });
    const items = proj.projects || (proj.projects = []);

    items.forEach((entry, i) => {
        list.appendChild(createProjectEntry(entry, i));
    });
}

function createProjectEntry(entry, index) {
    const div = document.createElement("div");
    div.className = "array-entry";

    const techs = entry.technologies || [];
    const techTagsHtml = techs
        .map(
            (t, ti) =>
                `<span class="tech-tag">${esc(t)}<button type="button" onclick="removeTech(${index}, ${ti})">×</button></span>`
        )
        .join("");

    div.innerHTML = `
        <div class="array-entry-header">
            <span class="array-entry-number">#${index + 1}</span>
            <button type="button" class="btn-danger btn-small" onclick="removeProject(${index})">REMOVE</button>
        </div>
        <div class="field">
            <label>TITLE</label>
            <input type="text" value="${esc(entry.title || "")}" data-proj-field="${index}" data-key="title">
        </div>
        <div class="field">
            <label>DESCRIPTION</label>
            <textarea data-proj-field="${index}" data-key="description">${esc(entry.description || "")}</textarea>
        </div>
        <div class="field">
            <label>STATUS</label>
            <input type="text" value="${esc(entry.status || "")}" data-proj-field="${index}" data-key="status">
        </div>
        <div class="field-group">
            <div class="field-group-title">TECHNOLOGIES</div>
            <div class="tech-tags" id="techs-${index}">${techTagsHtml}</div>
            <div class="tech-add">
                <input type="text" id="tech-input-${index}" placeholder="Add technology">
                <button type="button" class="btn-secondary btn-small" onclick="addTech(${index})">ADD</button>
            </div>
        </div>
    `;

    div.querySelectorAll("[data-proj-field]").forEach((el) => {
        el.addEventListener("input", () => {
            const idx = parseInt(el.dataset.projField);
            state.projects.projects[idx][el.dataset.key] = el.value;
        });
    });

    const techInput = div.querySelector(`#tech-input-${index}`);
    if (techInput) {
        techInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                addTech(index);
            }
        });
    }

    return div;
}

function addProject() {
    if (!state.projects) state.projects = { projects: [] };
    if (!state.projects.projects) state.projects.projects = [];
    state.projects.projects.push({
        title: "",
        description: "",
        technologies: [],
        status: "ongoing",
    });
    renderProjects();
}

function removeProject(index) {
    state.projects.projects.splice(index, 1);
    renderProjects();
}

function addTech(projIndex) {
    const input = document.getElementById("tech-input-" + projIndex);
    const val = input.value.trim();
    if (!val) return;
    state.projects.projects[projIndex].technologies.push(val);
    input.value = "";
    renderProjects();
}

function removeTech(projIndex, techIndex) {
    state.projects.projects[projIndex].technologies.splice(techIndex, 1);
    renderProjects();
}

// ---------------------------------------------------------------------------
// Payload
// ---------------------------------------------------------------------------
function collectPayload() {
    return {
        profile: state.profile || {},
        contact: state.contact || {},
        education: state.education || { education: [] },
        experience: state.experience || { experience: [] },
        projects: state.projects || { projects: [] },
    };
}

// ---------------------------------------------------------------------------
// API: Generate → Preview + Download
// ---------------------------------------------------------------------------
async function generatePDF() {
    const btn = document.getElementById("btn-generate");
    btn.classList.add("loading");
    btn.textContent = "GENERATING…";

    try {
        const res = await fetch("/api/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(collectPayload()),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || "Generation failed");
        }

        pdfBlob = await res.blob();

        // Extract filename from header
        const disposition = res.headers.get("content-disposition") || "";
        const match = disposition.match(/filename="?([^"]+)"?/);
        pdfBlob._filename = match ? match[1] : "resume.pdf";

        // Render in preview pane
        await renderPDFPreview(pdfBlob);
        toast("PDF GENERATED");
    } catch (e) {
        toast(e.message, true);
    } finally {
        btn.classList.remove("loading");
        btn.textContent = "GENERATE";
    }
}

// ---------------------------------------------------------------------------
// PDF.js Preview Rendering
// ---------------------------------------------------------------------------
async function renderPDFPreview(blob) {
    const pdfjsLib = await import("https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.min.mjs");
    pdfjsLib.GlobalWorkerOptions.workerSrc =
        "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.worker.min.mjs";

    const arrayBuffer = await blob.arrayBuffer();
    pdfDoc = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    totalPages = pdfDoc.numPages;
    currentPage = 1;

    // Show page nav
    const nav = document.getElementById("page-nav");
    if (nav) nav.style.display = "flex";

    const empty = document.getElementById("preview-empty");
    if (empty) empty.style.display = "none";

    // Render all pages
    const container = document.getElementById("preview-body");
    container.innerHTML = "";

    for (let i = 1; i <= totalPages; i++) {
        const page = await pdfDoc.getPage(i);
        const scale = 1.5;
        const viewport = page.getViewport({ scale });

        const canvas = document.createElement("canvas");
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        canvas.id = "pdf-page-" + i;
        container.appendChild(canvas);

        const ctx = canvas.getContext("2d");
        await page.render({ canvasContext: ctx, viewport }).promise;
    }

    updatePageIndicator();
}

function updatePageIndicator() {
    document.getElementById("page-indicator").textContent = `${currentPage} / ${totalPages}`;
}

function prevPage() {
    if (currentPage <= 1) return;
    currentPage--;
    scrollToPage(currentPage);
    updatePageIndicator();
}

function nextPage() {
    if (currentPage >= totalPages) return;
    currentPage++;
    scrollToPage(currentPage);
    updatePageIndicator();
}

function scrollToPage(num) {
    const canvas = document.getElementById("pdf-page-" + num);
    if (canvas) canvas.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------------------------------------------------------------------------
// Download PDF
// ---------------------------------------------------------------------------
function downloadPDF() {
    if (!pdfBlob) return;
    const url = URL.createObjectURL(pdfBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = pdfBlob._filename || "resume.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// API: Save to Backend
// ---------------------------------------------------------------------------
async function saveToBackend() {
    const btn = document.getElementById("btn-save");
    btn.classList.add("loading");
    btn.textContent = "SAVING…";

    try {
        const res = await fetch("/api/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(collectPayload()),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || "Save failed");
        }

        toast("SAVED TO BACKEND");
    } catch (e) {
        toast(e.message, true);
    } finally {
        btn.classList.remove("loading");
        btn.textContent = "SAVE TO BACKEND";
    }
}

// ---------------------------------------------------------------------------
// API: AI Tailoring
// ---------------------------------------------------------------------------
function updateProgress(pct, message) {
    const container = document.getElementById("tailor-progress");
    const fill = document.getElementById("progress-bar-fill");
    const text = document.getElementById("progress-text");
    if (container) container.style.display = "block";
    if (fill) fill.style.width = pct + "%";
    if (text) text.textContent = message;
}

function handlePipelineEvent(event) {
    const stageMap = {
        1: { pct: 10, label: "Stage 1/4: Analyzing job description..." },
        2: { pct: 35, label: "Stage 2/4: Matching resume to requirements..." },
        3: { pct: 65, label: "Stage 3/4: Tailoring resume sections..." },
        4: { pct: 90, label: "Stage 4/4: Validating output..." },
    };

    if (event.status === "error") {
        updateProgress(0, "Error: " + (event.message || "Unknown error"));
        return;
    }

    if (event.status === "in_progress") {
        const info = stageMap[event.stage];
        if (info) updateProgress(info.pct, event.message || info.label);
        return;
    }

    if (event.status === "complete") {
        const info = stageMap[event.stage];
        if (info) updateProgress(info.pct, (info.label.replace("...", "") + " done"));
    }
}

function applyTailoredData(data, isSkip) {
    if (isSkip) {
        const relScore = data.relevance || 'N/A';
        lastAiResultsHTML = `
            <div style="width:100%; text-align:left;">
                <div style="font-size:11px; text-transform:uppercase; margin-bottom:0.5rem; border-bottom:1px solid var(--border); padding-bottom:0.5rem;">
                    <span style="color:var(--fg); font-weight:bold;">AI TAILORING — SKIPPED (LOW MATCH)</span>
                    <span style="color:#e74c3c; font-weight:bold; float:right;">JD: ${relScore}/10</span>
                </div>
                ${data.relevance_analysis ? `<div style="font-size:11px; color:var(--muted); line-height:1.6;">${esc(data.relevance_analysis)}</div>` : ''}
            </div>`;
        showPreviewTabs();
        switchPreviewTab("ai");
        return;
    }

    // Stage results — don't apply to state yet
    pendingTailored = {
        profile: data.profile || null,
        experience: data.experience || null,
        projects: data.projects || null
    };

    // Compute diff: original snapshot vs pending tailored
    const beforeStr = JSON.stringify(originalSnapshot, null, 2);
    const afterStr = JSON.stringify(pendingTailored, null, 2);

    let diffHtml = "";
    if (window.Diff) {
        const diff = Diff.diffWords(beforeStr, afterStr);
        diffHtml = diff.map(part => {
            let style = part.added ? "color: #2ecc71; font-weight: bold; background: rgba(46, 204, 113, 0.1);" : part.removed ? "color: #e74c3c; text-decoration: line-through; background: rgba(231, 76, 60, 0.1);" : "color: #888;";
            return `<span style="${style}">${esc(part.value)}</span>`;
        }).join("");
    } else {
        diffHtml = `<span style="color: #f1c40f">Diff library failed to load.</span>`;
    }

    const relScore = data.relevance || 'N/A';
    const relColor = typeof relScore === 'number' && relScore >= 7 ? '#2ecc71' : typeof relScore === 'number' && relScore >= 4 ? '#f1c40f' : '#e74c3c';

    let evalHtml = "";
    if (data.eval_scores && typeof data.eval_scores === 'object') {
        const es = data.eval_scores;
        const formatVal = (v) => {
            if (Array.isArray(v)) return v.length === 0 ? "none" : v.join(", ");
            if (v && typeof v === "object") return JSON.stringify(v);
            if (typeof v === "number") return (v <= 1 && v >= 0) ? (v * 100).toFixed(0) + "%" : String(v);
            return String(v);
        };
        const tooltip = (label, text) => `<span class="tooltip-wrap">${esc(label)}<span class="tooltip-icon">?</span><span class="tooltip-text">${esc(text)}</span></span>`;
        const rows = [
            [tooltip("Alignment", "Token overlap between tailored resume and JD. Higher = more JD keywords matched. Healthy: 15-35%. Pass: ≥8%."), es.job_alignment_score],
            [tooltip("Preservation", "How much original content was kept (Jaccard similarity). Below 40% = heavy rewriting, hallucination risk. Healthy: 55-80%. Pass: ≥55%."), es.content_preservation],
        ];
        if (es.hallucinated_numbers && es.hallucinated_numbers.length > 0) {
            rows.push([tooltip("Hallucinated", "Numbers in tailored output NOT in original resume. These are suspicious fabricated metrics. Empty = clean."), es.hallucinated_numbers]);
        }
        if (es.immutable_violations && es.immutable_violations.length > 0) {
            rows.push([tooltip("Field violations", "Immutable fields (company, dates, location, URLs) that the LLM incorrectly modified. Must be zero."), es.immutable_violations]);
        }
        if (es.overall_pass !== undefined) {
            rows.push([tooltip("Overall", "All gates must pass: alignment ≥8%, preservation ≥55%, zero hallucinations, zero immutable violations, zero bullet count changes."), es.overall_pass ? "passed" : "needs review"]);
        }
        evalHtml = `<div style="font-size: 11px; margin-bottom: 0.75rem; padding-bottom: 0.75rem; border-bottom: 1px dashed var(--border);">
            <div style="text-transform: uppercase; color: var(--fg); margin-bottom: 0.35rem;">EVAL SCORES:</div>
            ${rows.map(([k, v]) => `<div style="color: var(--muted); display: flex; justify-content: space-between;"><span>${k}</span><span style="color: var(--fg);">${esc(formatVal(v))}</span></div>`).join("")}
        </div>`;
    }

    const hasPending = pendingTailored !== null;
    lastAiResultsHTML = `
        <div style="width: 100%; height: 100%; display: flex; flex-direction: column; text-align: left;">
            <div style="font-size: 11px; text-transform: uppercase; margin-bottom: 0.5rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; display: flex; justify-content: space-between; align-items: center;">
                <span style="color: var(--fg); font-weight: bold;">AI TAILORING RESULTS — REVIEW BEFORE APPLYING</span>
                <span style="color: ${relColor}; font-weight: bold; padding: 2px 6px; border: 1px solid ${relColor};">JD: ${relScore}/10</span>
            </div>
            ${data.relevance_analysis ? `<div style="font-size: 11px; color: var(--muted); margin-bottom: 0.75rem; padding-bottom: 0.75rem; border-bottom: 1px dashed var(--border); line-height: 1.6;">${esc(data.relevance_analysis)}</div>` : ''}
            ${evalHtml}
            <div style="font-size: 11px; text-transform: uppercase; color: var(--fg); margin-bottom: 0.5rem;">DIFF CHANGES:</div>
            <div style="position: relative; flex: 1; overflow-y: auto; min-height: 0;">
                <pre style="font-family: 'JetBrains Mono', monospace; font-size: 11px; background: #0a0a0a; padding: 0.5rem; white-space: pre-wrap; word-wrap: break-word; border: 1px solid var(--border); margin: 0;">${diffHtml}</pre>
                <div style="position: sticky; bottom: 0; display: flex; gap: 8px; padding: 8px; background: linear-gradient(transparent, var(--bg) 30%); margin-top: -2rem;">
                    <button onclick="applyPendingChanges()" style="flex: 1; padding: 8px; background: #2ecc71; color: #000; border: none; cursor: pointer; font-family: inherit; font-size: 11px; font-weight: bold; text-transform: uppercase;">Apply Changes</button>
                    <button onclick="discardPendingChanges()" style="flex: 1; padding: 8px; background: var(--bg); color: var(--fg); border: 1px solid var(--border); cursor: pointer; font-family: inherit; font-size: 11px; text-transform: uppercase;">Discard</button>
                    <button onclick="resetToOriginal()" style="padding: 8px 12px; background: var(--bg); color: var(--muted); border: 1px solid var(--border); cursor: pointer; font-family: inherit; font-size: 11px; text-transform: uppercase;" ${!originalSnapshot ? 'disabled' : ''}>Reset</button>
                </div>
            </div>
        </div>`;

    showPreviewTabs();
    switchPreviewTab("ai");
}

function applyPendingChanges() {
    if (!pendingTailored) return;
    if (pendingTailored.profile) Object.assign(state.profile, pendingTailored.profile);
    if (pendingTailored.experience) state.experience = pendingTailored.experience;
    if (pendingTailored.projects) state.projects = pendingTailored.projects;
    pendingTailored = null;

    populateScalarFields();
    renderExperience();
    renderProjects();
    generatePDF().then(() => switchPreviewTab("pdf"));
    toast("Changes applied to form fields.");
}

function discardPendingChanges() {
    pendingTailored = null;
    switchPreviewTab("pdf");
    toast("AI changes discarded.");
}

function resetToOriginal() {
    if (!originalSnapshot) return;
    state.profile = JSON.parse(JSON.stringify(originalSnapshot.profile));
    state.experience = JSON.parse(JSON.stringify(originalSnapshot.experience));
    state.projects = JSON.parse(JSON.stringify(originalSnapshot.projects));
    originalSnapshot = null;
    pendingTailored = null;

    populateScalarFields();
    renderExperience();
    renderProjects();
    generatePDF().then(() => switchPreviewTab("pdf"));
    toast("Reset to pre-tailoring state.");
}

async function tailorResume() {
    const jd = document.getElementById("ai-jd").value.trim();
    if (!jd) {
        toast("Please provide a Job Description", true);
        return;
    }

    const provider = document.getElementById("ai-provider").value;
    const model = document.getElementById("ai-model").value;
    const baseUrl = document.getElementById("ai-base-url").value;
    const apiKey = document.getElementById("ai-api-key").value;

    const btn = document.getElementById("btn-tailor");
    btn.classList.add("loading");
    btn.textContent = "TAILORING… (MAY TAKE A MINUTE)";

    try {
        const currentData = collectPayload();
        // Save snapshot for Reset functionality
        originalSnapshot = JSON.parse(JSON.stringify({
            profile: currentData.profile,
            experience: currentData.experience,
            projects: currentData.projects
        }));
        pendingTailored = null;

        const payload = {
            jd: jd,
            config: {
                provider: provider,
                model: model,
                base_url: baseUrl,
                api_key: apiKey
            },
            data: currentData
        };

        const res = await fetch("/api/tailor", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        if (!res.ok) {
            let errorMsg = "Tailoring failed";
            try {
                const err = await res.json();
                errorMsg = err.error || errorMsg;
            } catch (e) { }
            throw new Error(errorMsg);
        }

        // SSE streaming: read chunks from response body
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // Parse complete SSE lines from the buffer
            const lines = buffer.split("\n");
            // Keep the last potentially incomplete line in the buffer
            buffer = lines.pop();

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed || !trimmed.startsWith("data: ")) continue;
                const jsonStr = trimmed.slice("data: ".length);
                let event;
                try {
                    event = JSON.parse(jsonStr);
                } catch (e) {
                    continue;
                }

                // Error from pipeline
                if (event.status === "error") {
                    handlePipelineEvent(event);
                    throw new Error(event.message || "Pipeline error");
                }

                // Pipeline stage events
                if (event.stage !== "final") {
                    handlePipelineEvent(event);
                    continue;
                }

                // Final event
                if (event.stage === "final" && event.status === "complete") {
                    updateProgress(100, "Complete");
                    applyTailoredData(event.data, false);
                    toast("RESUME TAILORED SUCCESSFULLY");
                } else if (event.stage === "final" && event.status === "skip") {
                    updateProgress(100, "Skipped — relevance already high");
                    applyTailoredData(event.data, true);
                    toast("RESUME ALREADY A GOOD MATCH");
                }
            }
        }
    } catch (e) {
        toast(e.message, true);
    } finally {
        btn.classList.remove("loading");
        btn.textContent = "TAILOR RESUME (AI)";
        // Hide progress bar after a delay
        setTimeout(() => {
            const container = document.getElementById("tailor-progress");
            if (container) container.style.display = "none";
            const fill = document.getElementById("progress-bar-fill");
            if (fill) fill.style.width = "0";
        }, 3000);
    }
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------
function toast(msg, isError = false) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.className = "toast visible" + (isError ? " error" : "");
    clearTimeout(el._timer);
    el._timer = setTimeout(() => {
        el.className = "toast";
    }, 2500);
}

// ---------------------------------------------------------------------------
// Util
// ---------------------------------------------------------------------------
function esc(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
}
