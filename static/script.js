let transactions = [];
let expenseChart = null;
let incomeChart = null;

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

const CATEGORY_OPTIONS = {
    income: [
        { value: "Lương Ameno", label: "💰 Lương Ameno" },
        { value: "Lương Winggo", label: "💰 Lương Winggo" },
        { value: "Chi phí phát sinh", label: "🧾 Chi phí phát sinh" },
        { value: "Other", label: "📋 Other" }
    ],
    expense: [
        { value: "Đổ xăng", label: "⛽ Đổ xăng" },
        { value: "Ăn ngoài", label: "🍽️ Ăn ngoài" },
        { value: "Đi chợ", label: "🛒 Đi chợ" },
        { value: "Chi phí phát sinh", label: "🧾 Chi phí phát sinh" },
        { value: "Gửi xe", label: "🅿️ Gửi xe" },
        { value: "Đi chơi", label: "🎉 Đi chơi" },
        { value: "Trả nợ", label: "💳 Trả nợ" },
        { value: "Quỹ Ameno", label: "🏦 Quỹ Ameno" },
        { value: "Shopping online", label: "🛍️ Shopping online" },
        { value: "Other", label: "📋 Other" }
    ]
};

function populateCategoryOptions(type, selectedCategory) {
    const options = CATEGORY_OPTIONS[type] || [];

    categoryInput.innerHTML = "";

    options.forEach(({ value, label }) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        categoryInput.appendChild(option);
    });

    const values = options.map(option => option.value);

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
        const walletTransactions = transactions.filter(transaction => transaction.wallet === walletName);

        const income = walletTransactions
            .filter(transaction => transaction.type === "Income")
            .reduce((sum, transaction) => sum + Number(transaction.amount), 0);

        const expense = walletTransactions
            .filter(transaction => transaction.type === "Expense")
            .reduce((sum, transaction) => sum + Number(transaction.amount), 0);

        const incomeEl = document.getElementById(`wallet-${idPrefix}-income`);
        const expenseEl = document.getElementById(`wallet-${idPrefix}-expense`);
        const walletBalanceEl = document.getElementById(`wallet-${idPrefix}-balance`);

        if (incomeEl) incomeEl.textContent = formatMoney(income);
        if (expenseEl) expenseEl.textContent = formatMoney(expense);
        if (walletBalanceEl) walletBalanceEl.textContent = formatMoney(income - expense);
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
        typeCell.textContent = transaction.type;

        const categoryCell = document.createElement("td");
        categoryCell.textContent = transaction.category;

        const walletCell = document.createElement("td");
        walletCell.textContent = transaction.wallet;

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
    renderTable();
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
    populateCategoryOptions(type, transaction.category);
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
        category: categoryInput.value,
        wallet: walletInput.value,
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
    populateCategoryOptions(typeInput.value);
});

historyTypeFilter.addEventListener("change", renderTable);
historyMonthFilter.addEventListener("change", renderTable);
historyWalletFilter.addEventListener("change", renderTable);
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

loadTransactions().catch(error => {
    console.error(error);
    alert(error.message);
});

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