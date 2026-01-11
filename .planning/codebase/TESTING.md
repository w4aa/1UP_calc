# Testing Patterns

**Analysis Date:** 2026-01-11

## Test Framework

**Runner:**
- Python built-in testing approach (not pytest, not unittest module)
- Tests use plain functions with `test_` prefix
- Manual assertions with `assert` statements
- Print statements for test output

**Assertion Library:**
- Built-in `assert` statements
- Custom error messages: `assert condition, "error message"`

**Run Commands:**
```bash
python tests/test_system.py         # Run system integration tests
python tests/test_fts_engine.py     # Run FTS engine tests
python tests/test_runner.py         # Run engine runner tests
python tests/test_analyze.py        # Run analysis tests
```

## Test File Organization

**Location:**
- Separate `tests/` directory (not co-located with source)

**Naming:**
- `test_*.py` for all test files
- Examples: `test_system.py`, `test_fts_engine.py`, `test_runner.py`

**Structure:**
```
tests/
  ├── __init__.py
  ├── test_system.py              # Integration tests (imports, DB, engines)
  ├── test_fts_engine.py          # FTS engine unit tests
  ├── test_runner.py              # Engine runner tests
  ├── test_analyze.py             # Analysis tests
  └── test_analyze_engines.py     # Engine analysis tests
```

## Test Structure

**Suite Organization:**
```python
# tests/test_system.py
def test_imports():
    """Test that all critical imports work."""
    # test code
    print("[PASS] All imports successful")

def test_database():
    """Test database connectivity."""
    # test code
    print("[PASS] Database tests passed")

def main():
    """Run all tests."""
    tests = [test_imports, test_database, test_engine_runner]
    for test in tests:
        test()
```

**Patterns:**
- No setup/teardown (beforeEach/afterEach)
- Tests create temporary instances directly
- Manual orchestration via `main()` function
- Console output with `[OK]`, `[FAIL]`, `[PASS]` indicators

## Mocking

**Framework:**
- No mocking framework detected
- Tests use real database and actual engine objects

**Patterns:**
- No module mocking
- No function mocking
- Integration tests with real dependencies

**What to Mock:**
- Not applicable (no mocking used)

**What NOT to Mock:**
- Everything (tests use real implementations)

## Fixtures and Factories

**Test Data:**
- No formal fixtures detected
- Test data created inline in test functions
- Example from `tests/test_fts_engine.py`:
  ```python
  markets = {
      'home_1x2': 1.75, 'draw_1x2': 3.50, 'away_1x2': 4.50,
      'sporty_fts_home': 2.10, 'sporty_fts_away': 1.90,
      # ... more test data
  }
  ```

**Location:**
- Test data defined in test function scope
- No shared fixture files

## Coverage

**Requirements:**
- No coverage target defined
- Coverage not measured

**Configuration:**
- No coverage tool configuration

**View Coverage:**
- Not applicable (no coverage tooling)

## Test Types

**Unit Tests:**
- Scope: Test individual engine calculations
- Mocking: None (use real implementations)
- Examples: `tests/test_fts_engine.py` - tests FTS provider selection logic

**Integration Tests:**
- Scope: Test multiple modules together
- Mocking: None
- Examples: `tests/test_system.py` - tests imports, database, engine runner together

**E2E Tests:**
- Not present

## Common Patterns

**Async Testing:**
- Not detected (tests are synchronous)

**Error Testing:**
```python
# From tests/test_fts_engine.py
assert result_sporty is not None, "Sporty calculation failed"
assert result_sporty['fts_source'] == 'sporty', f"Wrong FTS source: {result_sporty['fts_source']}"
```

**Snapshot Testing:**
- Not used

---

*Testing analysis: 2026-01-11*
*Update when test patterns change*
