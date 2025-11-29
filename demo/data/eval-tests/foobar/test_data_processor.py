"""
Unit tests for the foobar data_processor module.
These tests should be framework-agnostic (work with both pandas and polars).
"""
import sys
from pathlib import Path

# Add foobar package to path
foobar_path = Path(__file__).parent.parent.parent / "repos" / "foobar"
sys.path.insert(0, str(foobar_path))

from data_processor import (
    load_data,
    filter_by_age,
    calculate_average_salary,
    group_by_department,
    add_bonus_column,
    sort_by_salary,
    get_top_n_earners,
    to_dict_list,
)


# Sample test data
SAMPLE_DATA = [
    {'name': 'Alice', 'age': 30, 'salary': 75000, 'department': 'Engineering'},
    {'name': 'Bob', 'age': 25, 'salary': 65000, 'department': 'Marketing'},
    {'name': 'Charlie', 'age': 35, 'salary': 85000, 'department': 'Engineering'},
    {'name': 'Diana', 'age': 28, 'salary': 70000, 'department': 'Sales'},
    {'name': 'Eve', 'age': 32, 'salary': 80000, 'department': 'Engineering'},
    {'name': 'Frank', 'age': 45, 'salary': 95000, 'department': 'Management'},
]


def test_load_data():
    """Test loading data from list of dicts - INTENTIONALLY FAILS ON ALL BRANCHES"""
    df = load_data(SAMPLE_DATA)
    assert len(df) == 6
    assert 'name' in df.columns
    assert 'age' in df.columns
    assert 'salary' in df.columns
    # This assertion will fail on all branches to verify scoring logic
    assert len(df) == 999, "Intentional failure to test scoring logic"


def test_filter_by_age():
    """Test filtering by minimum age"""
    df = load_data(SAMPLE_DATA)
    filtered = filter_by_age(df, min_age=30)
    assert len(filtered) == 4  # Alice(30), Charlie(35), Eve(32), Frank(45)


def test_filter_by_age_boundary():
    """Test filtering at exact age boundary"""
    df = load_data(SAMPLE_DATA)
    filtered = filter_by_age(df, min_age=28)
    assert len(filtered) == 5  # Everyone except Bob(25)


def test_calculate_average_salary():
    """Test calculating average salary"""
    df = load_data(SAMPLE_DATA)
    avg_salary = calculate_average_salary(df)
    expected = (75000 + 65000 + 85000 + 70000 + 80000 + 95000) / 6
    assert abs(avg_salary - expected) < 0.01


def test_calculate_average_salary_filtered():
    """Test average salary on filtered data"""
    df = load_data(SAMPLE_DATA)
    filtered = filter_by_age(df, min_age=30)
    avg_salary = calculate_average_salary(filtered)
    expected = (75000 + 85000 + 80000 + 95000) / 4
    assert abs(avg_salary - expected) < 0.01


def test_group_by_department():
    """Test grouping by department"""
    df = load_data(SAMPLE_DATA)
    grouped = group_by_department(df)

    # Convert to dict for easier assertion
    result_dict = {row['department']: row['salary'] for row in to_dict_list(grouped)}

    assert len(result_dict) == 4  # Engineering, Marketing, Sales, Management
    assert abs(result_dict['Engineering'] - 80000) < 0.01  # (75000 + 85000 + 80000) / 3
    assert abs(result_dict['Marketing'] - 65000) < 0.01
    assert abs(result_dict['Sales'] - 70000) < 0.01
    assert abs(result_dict['Management'] - 95000) < 0.01


def test_add_bonus_column():
    """Test adding bonus column with default percentage"""
    df = load_data(SAMPLE_DATA)
    df_with_bonus = add_bonus_column(df)

    assert 'bonus' in df_with_bonus.columns
    records = to_dict_list(df_with_bonus)

    # Check first record (Alice)
    alice = [r for r in records if r['name'] == 'Alice'][0]
    assert abs(alice['bonus'] - 7500) < 0.01  # 75000 * 0.1


def test_add_bonus_column_custom_percentage():
    """Test adding bonus column with custom percentage"""
    df = load_data(SAMPLE_DATA)
    df_with_bonus = add_bonus_column(df, bonus_percentage=0.15)

    records = to_dict_list(df_with_bonus)
    alice = [r for r in records if r['name'] == 'Alice'][0]
    assert abs(alice['bonus'] - 11250) < 0.01  # 75000 * 0.15


def test_sort_by_salary_descending():
    """Test sorting by salary in descending order (default)"""
    df = load_data(SAMPLE_DATA)
    sorted_df = sort_by_salary(df, ascending=False)

    records = to_dict_list(sorted_df)
    assert records[0]['name'] == 'Frank'  # 95000
    assert records[1]['name'] == 'Charlie'  # 85000
    assert records[-1]['name'] == 'Bob'  # 65000


def test_sort_by_salary_ascending():
    """Test sorting by salary in ascending order"""
    df = load_data(SAMPLE_DATA)
    sorted_df = sort_by_salary(df, ascending=True)

    records = to_dict_list(sorted_df)
    assert records[0]['name'] == 'Bob'  # 65000
    assert records[1]['name'] == 'Diana'  # 70000
    assert records[-1]['name'] == 'Frank'  # 95000


def test_get_top_n_earners_default():
    """Test getting top 5 earners (default)"""
    df = load_data(SAMPLE_DATA)
    top_earners = get_top_n_earners(df)

    assert len(top_earners) == 5
    records = to_dict_list(top_earners)
    assert records[0]['name'] == 'Frank'  # Highest earner


def test_get_top_n_earners_custom():
    """Test getting top 3 earners"""
    df = load_data(SAMPLE_DATA)
    top_earners = get_top_n_earners(df, n=3)

    assert len(top_earners) == 3
    records = to_dict_list(top_earners)
    names = [r['name'] for r in records]
    assert 'Frank' in names
    assert 'Charlie' in names
    assert 'Eve' in names


def test_to_dict_list():
    """Test converting DataFrame to list of dicts"""
    df = load_data(SAMPLE_DATA)
    result = to_dict_list(df)

    assert isinstance(result, list)
    assert len(result) == 6
    assert all(isinstance(item, dict) for item in result)
    assert all('name' in item for item in result)


def test_integration_filter_sort_top():
    """Integration test: filter, sort, and get top earners"""
    df = load_data(SAMPLE_DATA)

    # Filter employees aged 30+
    filtered = filter_by_age(df, min_age=30)

    # Get top 2 earners
    top_earners = get_top_n_earners(filtered, n=2)

    records = to_dict_list(top_earners)
    assert len(records) == 2
    assert records[0]['name'] == 'Frank'
    assert records[1]['name'] == 'Charlie'
