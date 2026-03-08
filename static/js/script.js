document.addEventListener("DOMContentLoaded", () => {
    const cache = new Map();
    const CACHE_EXPIRY = 5 * 60 * 1000;

    const getApiUrl = () => {
        const hostname = window.location.hostname;
        if (hostname === "chatpd-web.github.io" || hostname.includes("github.io")) {
            return "https://testweb.241814.xyz/chatpd";
        }
        if (hostname === "localhost" || hostname === "127.0.0.1") {
            return "";
        }
        return "https://testweb.241814.xyz/chatpd";
    };

    const getBaseUrl = () => {
        const path = window.location.pathname;
        if (path.includes("/chatpd-web/")) {
            return "/chatpd-web";
        }
        return "";
    };

    const apiUrl = getApiUrl();
    const baseUrl = getBaseUrl();

    const form = document.getElementById("search-form");
    const keywordsInput = document.getElementById("keywords");
    const sortByInput = document.getElementById("sort-by");
    const arxivFromInput = document.getElementById("arxiv-from");
    const arxivToInput = document.getElementById("arxiv-to");
    const resetButton = document.getElementById("reset-filters");
    const resultsList = document.getElementById("results-list");
    const resultsCount = document.getElementById("results-count");
    const pageInfo = document.getElementById("page-info");
    const prevPageBtn = document.getElementById("prev-page");
    const nextPageBtn = document.getElementById("next-page");
    const dataTypeFilter = document.getElementById("data-type-filter");
    const taskFilter = document.getElementById("task-filter");
    const dataStatusText = document.getElementById("data-status-text");
    const refreshDataStatusBtn = document.getElementById("refresh-data-status");

    let currentPage = 1;
    let totalPages = 1;
    let selectedDataType = "All";
    let selectedTask = "All";
    let activeRequestController = null;

    function getCachedData(key) {
        const item = cache.get(key);
        if (item && Date.now() - item.timestamp < CACHE_EXPIRY) {
            return item.data;
        }
        cache.delete(key);
        return null;
    }

    function setCachedData(key, data) {
        cache.set(key, { data, timestamp: Date.now() });
    }

    function debounce(func, wait) {
        let timeout;
        return (...args) => {
            clearTimeout(timeout);
            timeout = setTimeout(() => func(...args), wait);
        };
    }

    function escapeHtml(text) {
        return (text ?? "")
            .toString()
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function normalizeYymm(value) {
        const compact = (value || "").trim().replace(/\D/g, "");
        if (!compact) return "";
        if (/^\d{4}$/.test(compact)) return compact;
        return "";
    }

    function updateNavigationAndAssets() {
        document.querySelectorAll(".top-nav a").forEach((link) => {
            if (link.getAttribute("href") === "./") {
                link.setAttribute("href", baseUrl + "/" || "./");
            } else if (link.getAttribute("href") === "datasets") {
                link.setAttribute("href", baseUrl + "/datasets");
            }
        });
        const cssLink = document.getElementById("css-link");
        if (baseUrl && cssLink) {
            cssLink.href = `${baseUrl}/static/css/styles.css`;
        }
    }

    function showLoading() {
        resultsList.innerHTML = '<div class="loading">Loading...</div>';
    }

    function fetchDataStatus() {
        dataStatusText.textContent = "Data status loading...";
        fetch(`${apiUrl}/api/data-status`)
            .then((response) => response.json())
            .then((data) => {
                const totalRecords = Number(data.total_records || 0).toLocaleString();
                const totalDatasets = Number(data.total_datasets || 0).toLocaleString();
                const dbMtime = data.database_mtime || "N/A";
                dataStatusText.textContent =
                    `Updated: ${dbMtime} | Records: ${totalRecords} | Datasets: ${totalDatasets}`;
            })
            .catch((error) => {
                console.error("Error fetching data status:", error);
                dataStatusText.textContent = "Failed to fetch data status.";
            });
    }

    function updateActiveFilter(container, activeLink) {
        container.querySelectorAll(".filter-link").forEach((link) => link.classList.remove("active"));
        if (activeLink) {
            activeLink.classList.add("active");
        }
    }

    function buildConditions() {
        const conditions = [];
        if (selectedDataType !== "All") {
            conditions.push({ field: "data_type", match_mode: "exact", value: selectedDataType });
        }
        if (selectedTask !== "All") {
            conditions.push({ field: "task", match_mode: "exact", value: selectedTask });
        }
        return conditions;
    }

    function populateDataTypeFilter(dataTypes) {
        dataTypeFilter.querySelectorAll('.filter-link:not([data-type="All"])').forEach((link) => link.remove());
        dataTypes.forEach((item) => {
            const link = document.createElement("a");
            link.href = "#";
            link.dataset.type = item.data_type;
            link.textContent = `${item.data_type} (${item.count})`;
            link.className = "filter-link";
            if (item.data_type === selectedDataType) {
                link.classList.add("active");
            }
            link.addEventListener("click", (event) => {
                event.preventDefault();
                selectedDataType = item.data_type;
                currentPage = 1;
                updateActiveFilter(dataTypeFilter, link);
                fetchResults();
            });
            dataTypeFilter.appendChild(link);
        });
    }

    function populateTaskFilter(tasks) {
        taskFilter.querySelectorAll('.filter-link:not([data-task="All"])').forEach((link) => link.remove());
        tasks.forEach((item) => {
            const link = document.createElement("a");
            link.href = "#";
            link.dataset.task = item.task;
            link.textContent = `${item.task} (${item.count})`;
            link.className = "filter-link";
            if (item.task === selectedTask) {
                link.classList.add("active");
            }
            link.addEventListener("click", (event) => {
                event.preventDefault();
                selectedTask = item.task;
                currentPage = 1;
                updateActiveFilter(taskFilter, link);
                fetchResults();
            });
            taskFilter.appendChild(link);
        });
    }

    function initAllFilterLinks() {
        const dataTypeAllLink = dataTypeFilter.querySelector('a[data-type="All"]');
        const taskAllLink = taskFilter.querySelector('a[data-task="All"]');

        dataTypeAllLink?.addEventListener("click", (event) => {
            event.preventDefault();
            selectedDataType = "All";
            currentPage = 1;
            updateActiveFilter(dataTypeFilter, dataTypeAllLink);
            fetchResults();
        });

        taskAllLink?.addEventListener("click", (event) => {
            event.preventDefault();
            selectedTask = "All";
            currentPage = 1;
            updateActiveFilter(taskFilter, taskAllLink);
            fetchResults();
        });
    }

    function initializeFilters() {
        initAllFilterLinks();
        fetch(`${apiUrl}/api/filters`)
            .then((response) => response.json())
            .then((data) => {
                populateDataTypeFilter(data.top_data_types || []);
                populateTaskFilter(data.top_tasks || []);
                initAllFilterLinks();
            })
            .catch((error) => {
                console.error("Error fetching filters:", error);
            });
    }

    function displayResults(results) {
        if (!results || results.length === 0) {
            resultsList.innerHTML = '<div class="no-results">No results found.</div>';
            return;
        }

        const fragments = [];
        results.forEach((result) => {
            let displayTitle = (result.title || "").trim();
            if (!displayTitle || displayTitle === "None" || displayTitle === "null") {
                displayTitle = result.arxiv_id ? `arXiv:${result.arxiv_id}` : (result.dataset_name || "Research Study");
            }

            const titleHtml = result.arxiv_id
                ? `<h3><a href="https://arxiv.org/abs/${encodeURIComponent(result.arxiv_id)}" target="_blank" rel="noopener noreferrer">${escapeHtml(displayTitle)}</a></h3>`
                : `<h3>${escapeHtml(displayTitle)}</h3>`;

            let datasetHtml = "<p><strong>Dataset:</strong> N/A</p>";
            if (result.dataset_entity) {
                const datasetUrl = `${baseUrl}/dataset/${encodeURIComponent(result.dataset_entity)}`;
                datasetHtml = `<p><strong>Dataset:</strong> <a href="${datasetUrl}">${escapeHtml(result.dataset_entity)}</a></p>`;
            } else if (result.dataset_name) {
                datasetHtml = `<p><strong>Dataset:</strong> ${escapeHtml(result.dataset_name)}</p>`;
            }

            const extraFields = [
                result.arxiv_id
                    ? `<p><strong>arXiv ID:</strong> <a href="https://arxiv.org/abs/${encodeURIComponent(result.arxiv_id)}" target="_blank" rel="noopener noreferrer">${escapeHtml(result.arxiv_id)}</a></p>`
                    : "",
                result.task ? `<p><strong>Task:</strong> ${escapeHtml(result.task)}</p>` : "",
                result.data_type ? `<p><strong>Data Type:</strong> ${escapeHtml(result.data_type)}</p>` : "",
                result.dataset_summary ? `<p><strong>Summary:</strong> ${escapeHtml(result.dataset_summary)}</p>` : "",
            ]
                .filter(Boolean)
                .join("");

            fragments.push(`<article class="result-item">${titleHtml}${datasetHtml}${extraFields}</article>`);
        });
        resultsList.innerHTML = fragments.join("");
    }

    function updatePagination() {
        prevPageBtn.disabled = currentPage <= 1;
        nextPageBtn.disabled = currentPage >= totalPages || totalPages === 0;
        pageInfo.textContent = `Page ${Math.max(currentPage, 1)} / ${Math.max(totalPages, 1)}`;
    }

    function buildQueryParams() {
        const keywords = keywordsInput.value.trim();
        const params = new URLSearchParams({
            q: keywords,
            field: "all",
            match_mode: "contains",
            page: String(currentPage),
            per_page: "10",
            sort_by: sortByInput.value || "latest",
            include_stats: "false",
        });

        const conditions = buildConditions();
        if (conditions.length > 0) {
            params.set("conditions", JSON.stringify(conditions));
        }

        if (arxivFromInput.value) {
            const from = normalizeYymm(arxivFromInput.value);
            if (from) params.set("arxiv_from", from);
        }
        if (arxivToInput.value) {
            const to = normalizeYymm(arxivToInput.value);
            if (to) params.set("arxiv_to", to);
        }
        return params;
    }

    function fetchResults() {
        const params = buildQueryParams();
        const cacheKey = params.toString();
        const cached = getCachedData(cacheKey);
        if (cached) {
            displayResults(cached.results);
            totalPages = cached.total_pages || 1;
            resultsCount.textContent = `Search Results: ${cached.results_count} total items (${cached.results.length} items on this page)`;
            updatePagination();
            return;
        }

        if (activeRequestController) {
            activeRequestController.abort();
        }
        activeRequestController = new AbortController();

        showLoading();
        fetch(`${apiUrl}/api/query?${params.toString()}`, { signal: activeRequestController.signal })
            .then((response) => {
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return response.json();
            })
            .then((data) => {
                setCachedData(cacheKey, data);
                displayResults(data.results);
                totalPages = data.total_pages || 1;
                resultsCount.textContent = `Search Results: ${data.results_count} total items (${data.results.length} items on this page)`;
                updatePagination();
            })
            .catch((error) => {
                if (error.name === "AbortError") return;
                console.error("Error fetching results:", error);
                resultsList.innerHTML = '<div class="error">Error fetching results. Please try again.</div>';
                resultsCount.textContent = "Search Results: 0 total items (0 items on this page)";
                totalPages = 1;
                updatePagination();
            });
    }

    const debouncedSearch = debounce(() => {
        currentPage = 1;
        fetchResults();
    }, 350);

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        currentPage = 1;
        fetchResults();
    });
    keywordsInput.addEventListener("input", debouncedSearch);
    sortByInput.addEventListener("change", () => {
        currentPage = 1;
        fetchResults();
    });
    arxivFromInput.addEventListener("change", () => {
        arxivFromInput.value = normalizeYymm(arxivFromInput.value);
        currentPage = 1;
        fetchResults();
    });
    arxivToInput.addEventListener("change", () => {
        arxivToInput.value = normalizeYymm(arxivToInput.value);
        currentPage = 1;
        fetchResults();
    });

    prevPageBtn.addEventListener("click", () => {
        if (currentPage > 1) {
            currentPage -= 1;
            fetchResults();
        }
    });
    nextPageBtn.addEventListener("click", () => {
        if (currentPage < totalPages) {
            currentPage += 1;
            fetchResults();
        }
    });

    resetButton.addEventListener("click", () => {
        keywordsInput.value = "";
        sortByInput.value = "latest";
        arxivFromInput.value = "";
        arxivToInput.value = "";
        selectedDataType = "All";
        selectedTask = "All";
        updateActiveFilter(dataTypeFilter, dataTypeFilter.querySelector('a[data-type="All"]'));
        updateActiveFilter(taskFilter, taskFilter.querySelector('a[data-task="All"]'));
        currentPage = 1;
        fetchResults();
    });

    updateNavigationAndAssets();
    initializeFilters();
    fetchDataStatus();
    refreshDataStatusBtn?.addEventListener("click", fetchDataStatus);
    updatePagination();
    fetchResults();
});
