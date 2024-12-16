document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('search-form');
    const resultsList = document.getElementById('results-list');
    const resultsCount = document.getElementById('results-count');
    const pageSelector = document.getElementById('page-selector');
    const prevPageBtn = document.getElementById('prev-page');
    const nextPageBtn = document.getElementById('next-page');
    const dataTypeFilter = document.getElementById('data-type-filter');
    const taskFilter = document.getElementById('task-filter');

    let server_address = 'https://testweb.241814.xyz'
    let server_port = '5000'

    let currentPage = 1;
    let totalPages = 1;
    let selectedDataType = 'All';
    let selectedTask = 'All';
    let keywords = '';

    // 调用初始化函数
    // initializeFilters();

    // 初始化过滤器
    function initializeFilters() {
        // 获取 Data Types 和 Tasks
        fetch(`${server_address}:${server_port}/api/filters`)
            .then(response => response.json())
            .then(data => {
                populateDataTypeFilter(data.top_data_types);
                populateTaskFilter(data.top_tasks);
            })
            .catch(error => {
                console.error('Error fetching filters:', error);
            });
    }

    // 修正后的 Data Type 过滤器填充函数
    function populateDataTypeFilter(dataTypes) {
        dataTypes.forEach(item => {
            const link = document.createElement('a');
            link.href = '#';
            link.dataset.type = item.data_type;
            link.textContent = `${item.data_type} (${item.count})`; // 使用反引号
            link.classList.add('filter-link');
            if (item.data_type === selectedDataType) {
                link.classList.add('active');
            }
            link.addEventListener('click', (e) => {
                e.preventDefault();
                selectedDataType = item.data_type;
                currentPage = 1;
                updateActiveFilter(dataTypeFilter, link);
                updateHiddenInputs();
                fetchResults();
            });
            dataTypeFilter.appendChild(link);
        });
    }

    // 修正后的 Task 过滤器填充函数
    function populateTaskFilter(tasks) {
        tasks.forEach(item => {
            const link = document.createElement('a');
            link.href = '#';
            link.dataset.task = item.task;
            link.textContent = `${item.task} (${item.count})`; // 使用反引号
            link.classList.add('filter-link');
            if (item.task === selectedTask) {
                link.classList.add('active');
            }
            link.addEventListener('click', (e) => {
                e.preventDefault();
                selectedTask = item.task;
                currentPage = 1;
                updateActiveFilter(taskFilter, link);
                updateHiddenInputs();
                fetchResults();
            });
            taskFilter.appendChild(link);
        });
    }


    // 更新活动过滤器样式
    function updateActiveFilter(container, activeLink) {
        const links = container.querySelectorAll('.filter-link');
        links.forEach(link => link.classList.remove('active'));
        activeLink.classList.add('active');
    }

    // 更新隐藏的输入字段
    function updateHiddenInputs() {
        document.getElementById('data_type').value = selectedDataType;
        document.getElementById('task').value = selectedTask;
    }

    // 处理表单提交
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        keywords = document.getElementById('keywords').value.trim();
        currentPage = 1;
        fetchResults();
    });

    // 处理上一页按钮
    prevPageBtn.addEventListener('click', function() {
        if (currentPage > 1) {
            currentPage--;
            fetchResults();
        }
    });

    // 处理下一页按钮
    nextPageBtn.addEventListener('click', function() {
        if (currentPage < totalPages) {
            currentPage++;
            fetchResults();
        }
    });

    // 处理页码选择器
    pageSelector.addEventListener('change', function() {
        currentPage = parseInt(this.value);
        fetchResults();
    });

    // 获取并显示搜索结果
    function fetchResults() {
        const params = new URLSearchParams({
            keywords: keywords,
            data_type: selectedDataType,
            task: selectedTask,
            page: currentPage
        });

        // fetch(`http://101.201.77.95/:5003/api/search?${params.toString()}`)
        // fetch(`https://${server_ip}:${server_port}/api/search?${params.toString()}`)
        fetch(`${server_address}:${server_port}/api/search?${params.toString()}`)
            .then(response => response.json())
            .then(data => {
                displayResults(data.results);
                resultsCount.textContent = `Search Results: ${data.results_count} total items (${data.results.length} items on this page)`;
                totalPages = data.total_pages;
                populatePageSelector();
                updatePaginationButtons();
            })
            .catch(error => {
                console.error('Error fetching results:', error);
                resultsList.innerHTML = '<p>Error fetching results.</p>';
                resultsCount.textContent = 'Search Results: 0 total items (0 items on this page)';
            });
    }

    // 显示搜索结果
    function displayResults(results) {
        if (results.length > 0) {
            resultsList.innerHTML = '';
            results.forEach(result => {
                const item = document.createElement('div');
                item.className = 'result-item';

                // 构建 Dataset Name
                let datasetName = `<strong>Dataset Name:</strong> `;
                if (result.homepage) {
                    datasetName += `<a href="${result.homepage}" target="_blank">${result['dataset entity']}</a>`;
                } else {
                    datasetName += `<span>${result['dataset entity']}</span>`;
                }

                // 构建 Arxiv ID
                let arxivId = `<strong>arXiv ID:</strong> <a href="https://arxiv.org/abs/${result['arxiv id']}" target="_blank">${result['arxiv id']}</a>`;

                // 构建 Title
                let title = result.title ? `<p style="margin-top: 10px; font-size: 16px; color: #333;"><strong>Title:</strong> ${result.title}</p>` : '';

                // 构建其他字段
                let otherFields = '';
                const fields = [
                    { label: 'Dataset Summary', key: 'dataset summary' },
                    { label: 'Task', key: 'task' },
                    { label: 'Data Type', key: 'data type' },
                    { label: 'Dataset Citation', key: 'dataset citation' },
                    { label: 'Dataset Provider', key: 'dataset provider' },
                    { label: 'Dataset Publicly Available', key: 'dataset publicly available' },
                    { label: 'PapersWithCode URL', key: 'PapersWithCode URL', isLink: true },
                    { label: 'Other Useful Information', key: 'other useful information about this dataset' }
                ];

                fields.forEach(field => {
                    if (result[field.key]) {
                        if (field.isLink) {
                            otherFields += `<p><strong>${field.label}:</strong> <a href="${result[field.key]}" target="_blank">${result[field.key]}</a></p>`;
                        } else {
                            otherFields += `<p><strong>${field.label}:</strong> ${result[field.key]}</p>`;
                        }
                    }
                });

                item.innerHTML = `
                    <p>${datasetName}</p>
                    <p>${arxivId}</p>
                    ${title}
                    ${otherFields}
                `;
                resultsList.appendChild(item);
            });
        } else {
            resultsList.innerHTML = '<p>No results found.</p>';
        }
    }

    // 填充页码选择器
    function populatePageSelector() {
        pageSelector.innerHTML = '';
        for (let i = 1; i <= totalPages; i++) {
            const option = document.createElement('option');
            option.value = i;
            option.textContent = i;
            if (i === currentPage) {
                option.selected = true;
            }
            pageSelector.appendChild(option);
        }
    }

    // 更新分页按钮状态
    function updatePaginationButtons() {
        prevPageBtn.disabled = currentPage === 1;
        nextPageBtn.disabled = currentPage === totalPages;
    }

    // 初始化过滤器和加载初始结果
    initializeFilters();
    fetchResults();
});

