let transactions = [];
let expenseChart = null;
let incomeChart = null;
let trendChart = null;
let dbCategories = []; // Loaded from API

const form = document.getElementById("transaction-form");
const amountInput = document.getElementById("amount");
const typeInput = document.getElementById("type");
const categoryInput = document.getElementById("category");
const walletInput = document.getElementById("wallet");
const noteInput = document.getElementById("note");
const tbody = document.getElementById("transaction-list");
const totalIncomeEl = document.getElementById("total-income");
const totalExpenseEl = document.getElementById("total-expense");
const balanceEl = document.getElementById("balance");
const chartCanvas = document.getElementById("expenseChart");
const incomeChartCanvas = document.getElementById("incomeChart");
const historyTypeFilter = document.getElementById("history-type-filter");
const historyMonthFilter = document.getElementById("history-month-filter");
const historyWalletFilter = document.getElementById("history-wallet-filter");
const historySearch = document.getElementById("history-search");
const searchBtn = document.getElementById("search-btn");

const WALLET_ID_MAP = {
    "Tiền mặt": "cash",
    "Tài khoản tiết kiệm": "savings",
    "TK ngân hàng": "bank"
};
const submitBtn = document.getElementById("submit-btn");
const submitBtnLabel = document.getElementById("submit-btn-label");
const cancelEditBtn = document.getElementById("cancel-edit-btn");
const destinationWalletInput = document.getElementById("destination-wallet");
const destinationWalletGroup = document.getElementById("destination-wallet-group");
const categoryGroup = document.getElementById("category-group");

// Recurring UI selectors
const recurringForm = document.getElementById("recurring-form");
const recurringTypeSelect = document.getElementById("recurring-type");
const recurringAmountInput = document.getElementById("recurring-amount");
const recurringCategorySelect = document.getElementById("recurring-category");
const recurringWalletSelect = document.getElementById("recurring-wallet");
const recurringDestWalletSelect = document.getElementById("recurring-destination-wallet");
const recurringDestWalletGroup = document.getElementById("rec-destination-wallet-group");
const recurringCategoryGroup = document.getElementById("rec-category-group");
const recurringDayInput = document.getElementById("recurring-day");
const recurringNoteInput = document.getElementById("recurring-note");
const recurringListTbody = document.getElementById("recurring-list");

// Category UI selectors
const categoryForm = document.getElementById("category-form");
const categoryNameInput = document.getElementById("category-name");
const categoryTypeInput = document.getElementById("category-type");
const categorySubmitBtn = document.getElementById("category-submit-btn");
const categoryCancelBtn = document.getElementById("category-cancel-btn");
const categoryListTbody = document.getElementById("category-list");
const categoryFormTitle = document.getElementById("category-form-title");
const trendChartCanvas = document.getElementById("trendChart");

const budgetMonthFilter = document.getElementById("budget-month-filter");
const budgetItemsContainer = document.getElementById("budget-items-container");

let editingCategoryId = null;

const CATEGORY_COLOR_PALETTE = [
    "#f2789e", "#eb9c5c", "#6fc79a", "#8ec9e0",
    "#c99ee0", "#f3b95f", "#5cb99a", "#f39fc0",
    "#9a8cf0", "#e8607f", "#6ec6c4", "#f0a868"
];

const categoryColorMap = {};
let nextPaletteIndex = 0;

function getColorForCategory(category) {
    if (!categoryColorMap[category]) {
        categoryColorMap[category] = CATEGORY_COLOR_PALETTE[nextPaletteIndex % CATEGORY_COLOR_PALETTE.length];
        nextPaletteIndex += 1;
    }

    return categoryColorMap[category];
}

let editingId = null;

function populateCategoryOptions(type, selectedCategory) {
    const options = dbCategories.filter(cat => cat.type === type);

    categoryInput.innerHTML = "";

    options.forEach(cat => {
        const option = document.createElement("option");
        option.value = cat.name;
        option.textContent = (type === "income" ? "💰 " : "💸 ") + cat.name;
        categoryInput.appendChild(option);
    });

    const values = options.map(option => option.name);

    if (selectedCategory && values.includes(selectedCategory)) {
        categoryInput.value = selectedCategory;
    } else {
        categoryInput.selectedIndex = 0;
    }
}

function getCurrentMonthValue(date = new Date()) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    return `${year}-${month}`;
}

historyMonthFilter.value = getCurrentMonthValue();

function formatMoney(number) {
    return Number(number).toLocaleString("en-US") + " VND";
}

function parseAmount(value) {
    const rawNumber = Number(String(value).replace(/,/g, "").trim());
    return rawNumber * 1000;
}

function formatAmountInput(value) {
    const cleaned = String(value).replace(/[^\d]/g, "");

    if (!cleaned) {
        return "";
    }

    return Number(cleaned).toLocaleString("en-US");
}

function resetAmountInput() {
    amountInput.value = "";
}

function updateSummary() {
    const income = transactions
        .filter(transaction => transaction.type === "Income")
        .reduce((sum, transaction) => sum + Number(transaction.amount), 0);

    const expense = transactions
        .filter(transaction => transaction.type === "Expense")
        .reduce((sum, transaction) => sum + Number(transaction.amount), 0);

    totalIncomeEl.textContent = formatMoney(income);
    totalExpenseEl.textContent = formatMoney(expense);
    balanceEl.textContent = formatMoney(income - expense);

    updateWalletSummary();
}

function updateWalletSummary() {
    Object.entries(WALLET_ID_MAP).forEach(([walletName, idPrefix]) => {
        // Transactions outgoing or related to this wallet
        const walletTransactions = transactions.filter(transaction => transaction.wallet === walletName);
        
        // Incoming transfers specifically to this wallet
        const incomingTransfers = transactions.filter(transaction => transaction.type === "Transfer" && transaction.destination_wallet === walletName);

        const income = walletTransactions
            .filter(transaction => transaction.type === "Income")
            .reduce((sum, transaction) => sum + Number(transaction.amount), 0);

        const expense = walletTransactions
            .filter(transaction => transaction.type === "Expense")
            .reduce((sum, transaction) => sum + Number(transaction.amount), 0);

        const outgoingTransfersSum = walletTransactions
            .filter(transaction => transaction.type === "Transfer")
            .reduce((sum, transaction) => sum + Number(transaction.amount), 0);

        const incomingTransfersSum = incomingTransfers
            .reduce((sum, transaction) => sum + Number(transaction.amount), 0);

        // Balance = Income + Incoming Transfers - Expense - Outgoing Transfers
        const balanceVal = income + incomingTransfersSum - expense - outgoingTransfersSum;

        const incomeEl = document.getElementById(`wallet-${idPrefix}-income`);
        const expenseEl = document.getElementById(`wallet-${idPrefix}-expense`);
        const walletBalanceEl = document.getElementById(`wallet-${idPrefix}-balance`);

        if (incomeEl) incomeEl.textContent = formatMoney(income);
        if (expenseEl) expenseEl.textContent = formatMoney(expense);
        if (walletBalanceEl) walletBalanceEl.textContent = formatMoney(balanceVal);
    });
}

function updateChart() {
    const visibleTransactions = getVisibleTransactions();

    const incomeByCategory = visibleTransactions
        .filter(transaction => transaction.type === "Income")
        .reduce((accumulator, transaction) => {
            accumulator[transaction.category] = (accumulator[transaction.category] || 0) + Number(transaction.amount);
            return accumulator;
        }, {});

    const expenseByCategory = visibleTransactions
        .filter(transaction => transaction.type === "Expense")
        .reduce((accumulator, transaction) => {
            accumulator[transaction.category] = (accumulator[transaction.category] || 0) + Number(transaction.amount);
            return accumulator;
        }, {});

    if (incomeChart) {
        const incomeLabels = Object.keys(incomeByCategory);
        incomeChart.data.labels = incomeLabels;
        incomeChart.data.datasets[0].data = Object.values(incomeByCategory);
        incomeChart.data.datasets[0].backgroundColor = incomeLabels.map(getColorForCategory);
        incomeChart.update();
    }

    if (expenseChart) {
        const expenseLabels = Object.keys(expenseByCategory);
        expenseChart.data.labels = expenseLabels;
        expenseChart.data.datasets[0].data = Object.values(expenseByCategory);
        expenseChart.data.datasets[0].backgroundColor = expenseLabels.map(getColorForCategory);
        expenseChart.update();
    }

    updateTrendChart(visibleTransactions);
}

function updateTrendChart(visibleTransactions) {
    if (!trendChart) return;

    // Group transactions by date (YYYY-MM-DD)
    const grouped = {};
    visibleTransactions.forEach(t => {
        const dateStr = t.created_at ? t.created_at.split(" ")[0] : "";
        if (!dateStr) return;
        if (!grouped[dateStr]) {
            grouped[dateStr] = { income: 0, expense: 0 };
        }
        if (t.type === "Income") {
            grouped[dateStr].income += Number(t.amount);
        } else if (t.type === "Expense") {
            grouped[dateStr].expense += Number(t.amount);
        }
    });

    // Sort dates chronologically
    const sortedDates = Object.keys(grouped).sort();

    const incomeData = [];
    const expenseData = [];

    sortedDates.forEach(date => {
        incomeData.push(grouped[date].income);
        expenseData.push(grouped[date].expense);
    });

    trendChart.data.labels = sortedDates;
    trendChart.data.datasets[0].data = incomeData;
    trendChart.data.datasets[1].data = expenseData;
    trendChart.update();
}

function getVisibleTransactions() {
    const selectedType = historyTypeFilter.value;
    const selectedMonth = historyMonthFilter.value;
    const selectedWallet = historyWalletFilter.value;
    const searchText = historySearch ? historySearch.value.trim().toLowerCase() : "";

    return transactions.filter(transaction => {
        const matchesType = selectedType === "all" || transaction.type === selectedType;
        const matchesMonth = !selectedMonth || transaction.created_at.startsWith(selectedMonth);
        const matchesWallet = selectedWallet === "all" || transaction.wallet === selectedWallet;

        let matchesSearch = true;
        if (searchText) {
            const matchesNote = transaction.note && String(transaction.note).toLowerCase().includes(searchText);
            const matchesAmount = String(transaction.amount).includes(searchText);
            const matchesCategory = transaction.category && String(transaction.category).toLowerCase().includes(searchText);
            matchesSearch = matchesNote || matchesAmount || matchesCategory;
        }

        return matchesType && matchesMonth && matchesWallet && matchesSearch;
    });
}

function renderTable() {
    const visibleTransactions = getVisibleTransactions();

    tbody.innerHTML = "";

    if (visibleTransactions.length === 0) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");

        cell.colSpan = 7;
        cell.textContent = "No transactions found.";
        row.appendChild(cell);
        tbody.appendChild(row);
        updateSummary();
        updateChart();
        return;
    }

    visibleTransactions.forEach(transaction => {
        const row = document.createElement("tr");

        const typeCell = document.createElement("td");
        typeCell.textContent = transaction.type === "Transfer" ? "Transfer 🔄" : transaction.type;

        const categoryCell = document.createElement("td");
        categoryCell.textContent = transaction.category;

        const walletCell = document.createElement("td");
        if (transaction.type === "Transfer") {
            const fromWallet = transaction.wallet === "TK ngân hàng" ? "Tài khoản ngân hàng" : transaction.wallet;
            const toWallet = transaction.destination_wallet === "TK ngân hàng" ? "Tài khoản ngân hàng" : transaction.destination_wallet;
            walletCell.textContent = `${fromWallet} ➡️ ${toWallet}`;
        } else {
            walletCell.textContent = transaction.wallet === "TK ngân hàng" ? "Tài khoản ngân hàng" : transaction.wallet;
        }

        const amountCell = document.createElement("td");
        amountCell.textContent = formatMoney(transaction.amount);

        const dateCell = document.createElement("td");
        dateCell.textContent = transaction.created_at;

        const noteCell = document.createElement("td");
        noteCell.textContent = transaction.note;

        const actionCell = document.createElement("td");

        const editButton = document.createElement("button");
        editButton.type = "button";
        editButton.innerHTML = '<i class="fa-solid fa-pen"></i> Edit';
        editButton.classList.add("edit-btn");
        editButton.addEventListener("click", () => enterEditMode(transaction));
        actionCell.appendChild(editButton);

        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.innerHTML = '<i class="fa-solid fa-trash"></i> Delete';
        deleteButton.classList.add("delete-btn");
        deleteButton.addEventListener("click", () => deleteTransaction(transaction.id));
        actionCell.appendChild(deleteButton);

        if (transaction.id === editingId) {
            row.classList.add("editing-row");
        }

        row.appendChild(typeCell);
        row.appendChild(categoryCell);
        row.appendChild(walletCell);
        row.appendChild(amountCell);
        row.appendChild(dateCell);
        row.appendChild(noteCell);
        row.appendChild(actionCell);

        tbody.appendChild(row);
    });

    updateSummary();
    updateChart();
}

async function loadTransactions() {
    const response = await fetch("/api/transactions");

    if (!response.ok) {
        throw new Error("Failed to load transactions.");
    }

    transactions = await response.json();
    await loadCategories();
    if (budgetMonthFilter) {
        budgetMonthFilter.value = getCurrentMonthValue();
    }
    await loadBudgets();
    renderTable();
}

async function loadBudgets() {
    if (!budgetMonthFilter) return;
    const month = budgetMonthFilter.value;
    const response = await fetch(`/api/budgets?month=${month}`);
    if (!response.ok) {
        console.error("Failed to load budgets");
        return;
    }
    const budgets = await response.json();
    renderBudgets(budgets);
}

function renderBudgets(budgets) {
    if (!budgetItemsContainer) return;
    budgetItemsContainer.innerHTML = "";

    if (budgets.length === 0) {
        budgetItemsContainer.innerHTML = "<p>Vui lòng thêm danh mục chi tiêu trước.</p>";
        return;
    }

    budgets.forEach(b => {
        const percent = b.amount_limit > 0 ? (b.actual_spending / b.amount_limit) * 100 : 0;
        
        let statusClass = "status-safe";
        if (percent >= 100) {
            statusClass = "status-danger";
        } else if (percent >= 80) {
            statusClass = "status-warning";
        }

        const itemDiv = document.createElement("div");
        itemDiv.className = `budget-card ${statusClass}`;
        
        itemDiv.innerHTML = `
            <div class="budget-info">
                <span class="budget-cat-name">💸 ${b.category_name}</span>
                <span class="budget-ratio">${formatMoney(b.actual_spending)} / <span class="limit-label" id="limit-text-${b.category_name}">${b.amount_limit > 0 ? formatMoney(b.amount_limit) : "Chưa đặt"}</span></span>
            </div>
            <div class="budget-progress-bg">
                <div class="budget-progress-bar" style="width: ${Math.min(percent, 100)}%"></div>
            </div>
            <div class="budget-actions">
                <input type="text" placeholder="Đặt hạn mức..." id="input-limit-${b.category_name}" class="budget-input-field" value="${b.amount_limit > 0 ? b.amount_limit / 1000 : ""}">
                <button type="button" class="budget-save-btn" onclick="saveCategoryBudget('${b.category_name}')">
                    <i class="fa-solid fa-floppy-disk"></i>
                </button>
            </div>
            ${percent >= 100 ? '<span class="budget-warn-badge"><i class="fa-solid fa-triangle-exclamation"></i> ĐÃ VƯỢT HẠN MỨC!</span>' : percent >= 80 ? '<span class="budget-warn-badge warning"><i class="fa-solid fa-circle-exclamation"></i> Sắp vượt hạn mức!</span>' : ''}
        `;
        budgetItemsContainer.appendChild(itemDiv);
    });
}

async function saveCategoryBudget(categoryName) {
    const inputEl = document.getElementById(`input-limit-${categoryName}`);
    if (!inputEl) return;
    const value = inputEl.value.replace(/,/g, "").trim();
    if (!value || isNaN(value)) {
        alert("Vui lòng nhập hạn mức hợp lệ.");
        return;
    }
    const limitAmount = Number(value) * 1000;
    const month = budgetMonthFilter.value;

    try {
        const response = await fetch("/api/budgets", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                category_name: categoryName,
                month: month,
                amount_limit: limitAmount
            })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || "Không thể lưu ngân sách");
        }

        await loadBudgets();
    } catch (e) {
        alert(e.message);
    }
}

async function loadCategories() {
    const response = await fetch("/api/categories");
    if (!response.ok) {
        throw new Error("Failed to load categories.");
    }
    dbCategories = await response.json();
    populateCategoryOptions(typeInput.value);
    populateRecurringCategoryOptions(recurringTypeSelect ? recurringTypeSelect.value.toLowerCase() : "expense");
    renderCategoryList();
}

function populateRecurringCategoryOptions(type) {
    if (!recurringCategorySelect) return;
    const options = dbCategories.filter(cat => cat.type === type);
    recurringCategorySelect.innerHTML = "";
    options.forEach(cat => {
        const option = document.createElement("option");
        option.value = cat.name;
        option.textContent = cat.name;
        recurringCategorySelect.appendChild(option);
    });
}

function renderCategoryList() {
    if (!categoryListTbody) return;
    categoryListTbody.innerHTML = "";
    dbCategories.forEach(cat => {
        const row = document.createElement("tr");

        const nameCell = document.createElement("td");
        nameCell.textContent = cat.name;

        const typeCell = document.createElement("td");
        typeCell.textContent = cat.type === "income" ? "Income" : "Expense";

        const actionCell = document.createElement("td");

        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "edit-btn";
        editBtn.innerHTML = '<i class="fa-solid fa-pen"></i>';
        editBtn.addEventListener("click", () => enterCategoryEditMode(cat));

        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "delete-btn";
        deleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
        deleteBtn.addEventListener("click", () => deleteCategory(cat.id));

        actionCell.appendChild(editBtn);
        actionCell.appendChild(deleteBtn);

        row.appendChild(nameCell);
        row.appendChild(typeCell);
        row.appendChild(actionCell);

        categoryListTbody.appendChild(row);
    });
}

function enterCategoryEditMode(cat) {
    editingCategoryId = cat.id;
    categoryNameInput.value = cat.name;
    categoryTypeInput.value = cat.type;
    categorySubmitBtn.innerHTML = '<i class="fa-solid fa-check"></i> Update Category';
    categoryCancelBtn.hidden = false;
    categoryFormTitle.textContent = "Edit Category";
}

function exitCategoryEditMode() {
    editingCategoryId = null;
    categoryForm.reset();
    categorySubmitBtn.innerHTML = '<i class="fa-solid fa-plus"></i> Save Category';
    categoryCancelBtn.hidden = true;
    categoryFormTitle.textContent = "Add Category";
}

async function deleteCategory(id) {
    if (!confirm("Are you sure you want to delete this category?")) return;
    const response = await fetch(`/api/categories/${id}`, { method: "DELETE" });
    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        alert(error.detail || "Failed to delete category.");
        return;
    }
    await loadCategories();
}

async function createTransaction(payload) {
    const response = await fetch("/api/transactions", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || "Failed to save transaction.");
    }

    return response.json();
}

async function updateTransaction(id, payload) {
    const response = await fetch(`/api/transactions/${id}`, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || "Failed to update transaction.");
    }

    return response.json();
}

function enterEditMode(transaction) {
    editingId = transaction.id;

    const type = transaction.type.toLowerCase();
    typeInput.value = type;
    
    if (type === "transfer") {
        if (categoryGroup) categoryGroup.style.display = "none";
        if (destinationWalletGroup) destinationWalletGroup.style.display = "block";
        if (destinationWalletInput) destinationWalletInput.value = transaction.destination_wallet || "";
    } else {
        if (categoryGroup) categoryGroup.style.display = "block";
        if (destinationWalletGroup) destinationWalletGroup.style.display = "none";
        populateCategoryOptions(type, transaction.category);
    }
    
    walletInput.value = transaction.wallet;
    noteInput.value = transaction.note === "-" ? "" : transaction.note;
    amountInput.value = formatAmountInput(String(transaction.amount / 1000));

    submitBtnLabel.textContent = "Update Transaction";
    cancelEditBtn.hidden = false;

    renderTable();
    form.scrollIntoView({ behavior: "smooth", block: "start" });
}

function exitEditMode() {
    editingId = null;
    form.reset();
    resetAmountInput();
    if (categoryGroup) categoryGroup.style.display = "block";
    if (destinationWalletGroup) destinationWalletGroup.style.display = "none";
    populateCategoryOptions(typeInput.value);

    submitBtnLabel.textContent = "Add Transaction";
    cancelEditBtn.hidden = true;

    renderTable();
}

async function deleteTransaction(id) {
    const response = await fetch(`/api/transactions/${id}`, {
        method: "DELETE"
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || "Failed to delete transaction.");
    }

    transactions = transactions.filter(transaction => transaction.id !== id);
    renderTable();
}

form.addEventListener("submit", async event => {
    event.preventDefault();

    const amount = parseAmount(amountInput.value);

    if (!amount || Number.isNaN(amount)) {
        return;
    }

    const payload = {
        type: typeInput.value,
        category: typeInput.value === "transfer" ? "Chuyển ví" : categoryInput.value,
        wallet: walletInput.value,
        destination_wallet: typeInput.value === "transfer" ? destinationWalletInput.value : null,
        amount,
        note: noteInput.value.trim()
    };

    try {
        if (editingId) {
            const updatedTransaction = await updateTransaction(editingId, payload);
            const index = transactions.findIndex(transaction => transaction.id === editingId);

            if (index !== -1) {
                transactions[index] = updatedTransaction;
            }

            exitEditMode();
        } else {
            const savedTransaction = await createTransaction(payload);

            transactions.unshift(savedTransaction);
            form.reset();
            resetAmountInput();
            populateCategoryOptions(typeInput.value);
            renderTable();
        }
    } catch (error) {
        console.error(error);
        alert(error.message);
    }
});

cancelEditBtn.addEventListener("click", () => {
    exitEditMode();
});

amountInput.addEventListener("focus", () => {
    amountInput.select();
});

amountInput.addEventListener("input", () => {
    amountInput.value = formatAmountInput(amountInput.value);
});

typeInput.addEventListener("change", () => {
    const type = typeInput.value;
    if (type === "transfer") {
        if (categoryGroup) categoryGroup.style.display = "none";
        if (destinationWalletGroup) destinationWalletGroup.style.display = "block";
    } else {
        if (categoryGroup) categoryGroup.style.display = "block";
        if (destinationWalletGroup) destinationWalletGroup.style.display = "none";
        populateCategoryOptions(type);
    }
});

historyTypeFilter.addEventListener("change", renderTable);
historyMonthFilter.addEventListener("change", renderTable);
historyWalletFilter.addEventListener("change", renderTable);
if (budgetMonthFilter) {
    budgetMonthFilter.addEventListener("change", loadBudgets);
}
window.saveCategoryBudget = saveCategoryBudget;

if (historySearch) {
    historySearch.addEventListener("input", renderTable);
    historySearch.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            renderTable();
        }
    });
}
if (searchBtn) {
    searchBtn.addEventListener("click", renderTable);
}

// Category form listeners
if (categoryForm) {
    categoryForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const name = categoryNameInput.value.trim();
        const type = categoryTypeInput.value;
        if (!name) return;

        const payload = { name, type };
        try {
            if (editingCategoryId) {
                // Update
                const response = await fetch(`/api/categories/${editingCategoryId}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                if (!response.ok) {
                    const err = await response.json().catch(() => ({}));
                    throw new Error(err.detail || "Failed to update category.");
                }
            } else {
                // Create
                const response = await fetch("/api/categories", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                if (!response.ok) {
                    const err = await response.json().catch(() => ({}));
                    throw new Error(err.detail || "Failed to create category.");
                }
            }
            exitCategoryEditMode();
            await loadCategories();
            renderTable();
        } catch (error) {
            console.error(error);
            alert(error.message);
        }
    });
}

if (categoryCancelBtn) {
    categoryCancelBtn.addEventListener("click", exitCategoryEditMode);
}

resetAmountInput();
populateCategoryOptions(typeInput.value);

const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: {
            position: "right",
            labels: {
                usePointStyle: true,
                pointStyle: "circle",
                boxWidth: 10,
                padding: 14,
                color: "#6e3a50",
                font: {
                    size: 13
                }
            }
        }
    }
};

expenseChart = new Chart(chartCanvas, {
    type: "pie",
    data: {
        labels: [],
        datasets: [{
            data: [],
            backgroundColor: [],
            borderColor: "#fffbfc",
            borderWidth: 2
        }]
    },
    options: chartOptions
});

incomeChart = new Chart(incomeChartCanvas, {
    type: "pie",
    data: {
        labels: [],
        datasets: [{
            data: [],
            backgroundColor: [],
            borderColor: "#fffbfc",
            borderWidth: 2
        }]
    },
    options: chartOptions
});

if (trendChartCanvas) {
    trendChart = new Chart(trendChartCanvas, {
        type: "line",
        data: {
            labels: [],
            datasets: [
                {
                    label: "Thu nhập (Income)",
                    data: [],
                    borderColor: "#6fc79a",
                    backgroundColor: "rgba(111, 199, 154, 0.1)",
                    borderWidth: 3,
                    fill: true,
                    tension: 0.3
                },
                {
                    label: "Chi tiêu (Expense)",
                    data: [],
                    borderColor: "#ea6a8c",
                    backgroundColor: "rgba(234, 106, 140, 0.1)",
                    borderWidth: 3,
                    fill: true,
                    tension: 0.3
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: "top",
                    labels: {
                        color: "#6e3a50",
                        font: { size: 13, weight: "bold" }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: "#9a6b80" }
                },
                y: {
                    grid: { color: "rgba(216, 92, 133, 0.1)" },
                    ticks: { color: "#9a6b80" }
                }
            }
        }
    });
}

loadTransactions().then(() => {
    loadRecurring();
}).catch(error => {
    console.error(error);
    alert(error.message);
});

async function loadRecurring() {
    const response = await fetch("/api/recurring");
    if (!response.ok) return;
    const items = await response.json();
    renderRecurringList(items);
}

function renderRecurringList(items) {
    if (!recurringListTbody) return;
    recurringListTbody.innerHTML = "";
    items.forEach(r => {
        const row = document.createElement("tr");

        const typeCell = document.createElement("td");
        typeCell.textContent = r.type;

        const amountCell = document.createElement("td");
        amountCell.textContent = formatMoney(r.amount);

        const catNoteCell = document.createElement("td");
        catNoteCell.textContent = `${r.category} | ${r.note}`;

        const walletCell = document.createElement("td");
        if (r.type === "Transfer") {
            walletCell.textContent = `${r.wallet} ➡️ ${r.destination_wallet}`;
        } else {
            walletCell.textContent = r.wallet;
        }

        const dayCell = document.createElement("td");
        dayCell.textContent = `Ngày ${r.day_of_month}`;

        const runCell = document.createElement("td");
        runCell.textContent = r.last_executed_month || "Chưa chạy";

        const actionCell = document.createElement("td");
        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "delete-btn";
        deleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
        deleteBtn.addEventListener("click", async () => {
            if (!confirm("Xóa cấu hình định kỳ này?")) return;
            const res = await fetch(`/api/recurring/${r.id}`, { method: "DELETE" });
            if (res.ok) {
                loadRecurring();
            }
        });
        actionCell.appendChild(deleteBtn);

        row.appendChild(typeCell);
        row.appendChild(amountCell);
        row.appendChild(catNoteCell);
        row.appendChild(walletCell);
        row.appendChild(dayCell);
        row.appendChild(runCell);
        row.appendChild(actionCell);

        recurringListTbody.appendChild(row);
    });
}

// Bind recurring event listeners
if (recurringTypeSelect) {
    recurringTypeSelect.addEventListener("change", () => {
        const type = recurringTypeSelect.value.toLowerCase();
        if (type === "transfer") {
            if (recurringCategoryGroup) recurringCategoryGroup.style.display = "none";
            if (recurringDestWalletGroup) recurringDestWalletGroup.style.display = "block";
        } else {
            if (recurringCategoryGroup) recurringCategoryGroup.style.display = "block";
            if (recurringDestWalletGroup) recurringDestWalletGroup.style.display = "none";
            populateRecurringCategoryOptions(type);
        }
    });
}

if (recurringAmountInput) {
    recurringAmountInput.addEventListener("input", () => {
        recurringAmountInput.value = formatAmountInput(recurringAmountInput.value);
    });
}

if (recurringForm) {
    recurringForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const amount = parseAmount(recurringAmountInput.value);
        if (!amount || isNaN(amount)) return;

        const payload = {
            type: recurringTypeSelect.value,
            amount: amount,
            category: recurringTypeSelect.value === "Transfer" ? "Chuyển ví" : recurringCategorySelect.value,
            wallet: recurringWalletSelect.value,
            destination_wallet: recurringTypeSelect.value === "Transfer" ? recurringDestWalletSelect.value : null,
            day_of_month: parseInt(recurringDayInput.value),
            note: recurringNoteInput.value.trim()
        };

        try {
            const res = await fetch("/api/recurring", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || "Không thể thêm cấu hình");
            }

            recurringForm.reset();
            if (recurringCategoryGroup) recurringCategoryGroup.style.display = "block";
            if (recurringDestWalletGroup) recurringDestWalletGroup.style.display = "none";
            populateRecurringCategoryOptions(recurringTypeSelect.value.toLowerCase());
            await loadRecurring();
            await loadTransactions();
        } catch (error) {
            alert(error.message);
        }
    });
}

// Backup Dropdown Logic
const backupBtn = document.getElementById("backup-btn");
const backupDropdown = document.getElementById("backup-dropdown");

if (backupBtn && backupDropdown) {
    backupBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        backupDropdown.classList.toggle("show");
    });

    document.addEventListener("click", (e) => {
        if (!backupBtn.contains(e.target) && !backupDropdown.contains(e.target)) {
            backupDropdown.classList.remove("show");
        }
    });
}

// Top Tabs switching logic
document.querySelectorAll(".top-tabs-bar .tab-btn").forEach(button => {
    button.addEventListener("click", () => {
        // Remove active class from all tab buttons
        document.querySelectorAll(".top-tabs-bar .tab-btn").forEach(btn => btn.classList.remove("active"));
        // Add active class to clicked button
        button.classList.add("active");

        // Hide all tab panes
        document.querySelectorAll(".tab-pane").forEach(pane => pane.classList.remove("active"));
        // Show corresponding tab pane
        const targetTabId = button.getAttribute("data-tab");
        const targetPane = document.getElementById(targetTabId);
        if (targetPane) {
            targetPane.classList.add("active");
        }
    });
});

// JSON Import logic
const importJsonInput = document.getElementById("import-json-file");
if (importJsonInput) {
    importJsonInput.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = async (event) => {
            try {
                const data = JSON.parse(event.target.result);
                
                let itemCount = 0;
                if (Array.isArray(data)) {
                    itemCount = data.length;
                } else if (data && typeof data === "object") {
                    itemCount = (data.transactions?.length || 0) + (data.categories?.length || 0) + (data.budgets?.length || 0) + (data.recurring?.length || 0);
                }

                // Show confirming prompt
                if (!confirm(`Bạn có chắc chắn muốn nhập dữ liệu backup (${itemCount} mục) từ file JSON này? Dữ liệu hiện tại sẽ được bảo lưu.`)) {
                    importJsonInput.value = "";
                    return;
                }

                const response = await fetch("/api/backup/import", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(data)
                });

                if (!response.ok) {
                    const err = await response.json().catch(() => ({}));
                    throw new Error(err.detail || "Nhập file thất bại.");
                }

                const result = await response.json();
                alert(result.message || "Nhập dữ liệu thành công!");
                
                // Reload transactions, categories, budgets, and recurring settings across all tabs
                await loadTransactions();
                if (typeof loadCategories === "function") {
                    await loadCategories();
                }
                if (typeof loadBudgets === "function") {
                    await loadBudgets();
                }
                if (typeof loadRecurring === "function") {
                    await loadRecurring();
                }

                // Close backup dropdown
                if (backupDropdown) {
                    backupDropdown.classList.remove("show");
                }

            } catch (error) {
                alert("Lỗi: " + error.message);
            } finally {
                importJsonInput.value = "";
            }
        };
        reader.readAsText(file);
    });
}

// CSV Import logic
const importCsvInput = document.getElementById("import-csv-file");
if (importCsvInput) {
    importCsvInput.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        if (!confirm(`Bạn có chắc chắn muốn nhập dữ liệu từ file CSV "${file.name}"? Dữ liệu hiện tại sẽ được bảo lưu.`)) {
            importCsvInput.value = "";
            return;
        }

        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await fetch("/api/backup/import-csv", {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.detail || "Nhập file CSV thất bại.");
            }

            const result = await response.json();
            alert(result.message || "Nhập file CSV thành công!");

            // Reload all data
            await loadTransactions();
            if (typeof loadCategories === "function") await loadCategories();
            if (typeof loadBudgets === "function") await loadBudgets();
            if (typeof loadRecurring === "function") await loadRecurring();

            if (backupDropdown) backupDropdown.classList.remove("show");
        } catch (error) {
            alert("Lỗi: " + error.message);
        } finally {
            importCsvInput.value = "";
        }
    });
}