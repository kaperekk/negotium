# Negotium Refactoring & Architecture Modernization Plan

This plan outlines the step-by-step transformation of the codebase from its current script-style / procedural state into a clean, maintainable, modular, and fully typed architecture without breaking existing functionality.

---

## Phase 1: Domain Models & Static Typing Foundation
Introduce explicit data structures to replace ad-hoc dictionary passing across the codebase.

- [ ] **1.1. Core Domain Models (`src/domain/models.py`)**
  - Define `@dataclass(slots=True)` / `NamedTuple` models:
    - `LedgerEntry`: `ticker: str`, `amount: float`, `account_operation: bool = False`
    - `Transaction`: `date: str` (ISO), `entries: list[LedgerEntry]`
    - `AssetHolding`: `ticker: str`, `amount: float`, `price: float`, `currency: str`, `value_native: float`, `value_base: float`
    - `PortfolioSnapshot`: `date: str`, `assets: list[AssetHolding]`, `total_value: float`, `invested: float`, `base_currency: str`
    - `TickerMeta`: `ticker: str`, `name: str`, `sector: str`, `country: str`, `asset_class: str`
  - Implement fast serialization/deserialization helpers compatible with `orjson`.

- [ ] **1.2. Currency & Domain Constants (`src/domain/currencies.py`)**
  - Move currency definitions, exchange suffix mappings, triangulation lists, and currency symbols from `src/currencies.py` into `src/domain/currencies.py`.
  - Maintain backwards-compatibility alias exports.

- [ ] **1.3. Domain Exceptions (`src/domain/exceptions.py`)**
  - Define custom domain errors (`CorruptedLedgerError`, `InvalidImportFormatError`, `PriceFetchError`, `ProjectNotFoundError`).

---

## Phase 2: Decoupled Storage & Project Context
Eliminate global mutable project states and hidden disk layout dependencies from computation modules.

- [ ] **2.1. Project Context & Path Resolver (`src/storage/context.py`)**
  - Create `ProjectContext` class encapsulating project identification, root directory, data paths, and imports paths.
  - Abstract Streamlit session state access so storage operations work identically in CLI/tests without mocking UI state.

- [ ] **2.2. Typed Repository Layer (`src/storage/repositories.py`)**
  - `TransactionRepository`:
    - Thread-safe read/write/append operations for `transactions.jsonl`.
    - Typed query methods (`get_all() -> list[Transaction]`, `get_by_date()`, `get_tickers()`).
  - `SnapshotRepository`:
    - Read/write/invalidate operations for `portfolio.jsonl` and `benchmarks_{ccy}.json`.
  - `BalanceRepository`:
    - Storage and retrieval of `balance.json` (cached holdings and cost basis).
  - `PriceCacheRepository`:
    - Access to raw closes (`data/prices/`), adjusted closes (`data/prices_adj/`), and ticker metadata.

- [ ] **2.3. Remove Circular Imports & Clean Compatibility Exports (`src/storage/__init__.py`)**
  - Remove all inline `from ... import` statements.
  - Provide a clean facade for existing callers while migrating code to repositories.

---

## Phase 3: Market Data & FX Provider Layer
Consolidate fragmented caching, currency conversions, and Yahoo Finance downloads.

- [ ] **3.1. Unified Market Data Interface (`src/market_data/provider.py`)**
  - Create `MarketDataProvider` class responsible for:
    - Thread-safe, unified RAM price slab cache (`_PriceCache`).
    - FX cross-rate resolution with built-in triangulation (via USD) and caching.
    - Dividend history and ATH resolution.
  - Eliminate redundant passing of manual `fx_cache: dict` and `price_cache: dict` instances throughout core and UI layers.

- [ ] **3.2. Batched Downloader & Yahoo Client (`src/market_data/downloader.py`)**
  - Isolate `yfinance` download logic, stdout/stderr suppression, and retry handlers.
  - Expose clean methods: `ensure_prices(tickers, start_date, end_date, adjusted=False)`.

---

## Phase 4: Core Engine & Calculation Services
Refactor ledger maintenance and portfolio time-series algorithms into testable services.

- [ ] **4.1. Ledger Engine Refactoring (`src/services/ledger_service.py`)**
  - Refactor `src/ledger_core.py` to use domain models and `TransactionRepository`.
  - Encapsulate balance replay, average cost calculation (weighted-average price), and transaction insertion logic.
  - Refactor performance metrics (`compute_twr`, `annualize_twr`, `compute_irr`) to operate on `PortfolioSnapshot` structures and `MarketDataProvider`.

- [ ] **4.2. Portfolio Builder Engine (`src/services/portfolio_service.py`)**
  - Refactor `build_portfolio` forward pass:
    - Utilize `MarketDataProvider` for price and FX conversions.
    - Return typed `list[PortfolioSnapshot]`.
    - Clean snapshot caching and date-range slicing logic.

---

## Phase 5: Standardized Broker Importer Pipeline
Unify format parsing, validation, and transaction ingestion across brokers.

- [ ] **5.1. Base Importer Specification (`src/services/importers/base.py`)**
  - Define `BaseBrokerImporter` abstract class:
    - `validate(file_path: Path) -> ValidationResult`
    - `parse(file_path: Path, currency: str) -> list[Transaction]`
  - Provide common ticker translation and duplicate deduplication helpers.

- [ ] **5.2. Broker Parser Refactoring (`src/services/importers/`)**
  - Refactor `xtb_import.py` -> `src/services/importers/xtb.py`.
  - Refactor `bossa_import.py` -> `src/services/importers/bossa.py`.
  - Refactor `manual_import.py` -> `src/services/importers/manual.py`.

- [ ] **5.3. Import Manager Service (`src/services/import_service.py`)**
  - Create orchestrator to auto-detect broker formats, run imports across `data/{project}/imports/`, and trigger balance/snapshot rebuilds automatically.

---

## Phase 6: Streamlined Presentation Layer (UI)
Strip business logic and cache mechanics out of Streamlit components.

- [ ] **6.1. UI State & Runtime Coordinator (`src/ui/runtime.py`)**
  - Initialize services (`PortfolioService`, `MarketDataProvider`, `ImportService`) inside runtime context.
  - Remove direct session-state cache purging from individual UI widgets.

- [ ] **6.2. Decouple Dashboard & Sidebar (`src/ui/dashboard.py`, `src/ui/sidebar.py`)**
  - Delegate download workflows, data refreshes, and portfolio builds to service layer calls.
  - Keep dashboard and sidebar purely focused on layout, input capture, and chart rendering.

- [ ] **6.3. Component Cleanup (`src/ui/holdings.py`, `src/ui/trade_history.py`, `src/ui/allocation.py`)**
  - Update table renderers and charts to consume typed domain models (`AssetHolding`, `PortfolioSnapshot`).

---

## Phase 7: Verification, Test Suite & Documentation
Ensure 100% feature parity, performance preservation, and documentation accuracy.

- [ ] **7.1. Full Test Suite Validation**
  - Run all unit and integration tests (`pytest`).
  - Verify performance download benchmarks (`tests/test_performance_download.py`).
  - Add unit tests for new domain models, repositories, and importer interfaces.

- [ ] **7.2. Architecture Documentation Update (`ARCHITECTURE.md`)**
  - Update module maps, dependency diagrams, and flow descriptions to reflect the clean layered architecture.