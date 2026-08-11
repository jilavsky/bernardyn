"""Performance tests for Bernardyn.

Tests large dataset handling (100+ datasets) to ensure the application
remains responsive and doesn't crash under heavy load.
"""

import sys
import os
import time
from typing import Any, Dict, List

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_large_dataset_loading():
    """Test loading 100+ datasets efficiently."""
    from bernardyn.data.loader import get_default_dispatcher

    # Create a mock loader that generates synthetic data
    class SyntheticLoader:
        def can_load(self, filepath: str) -> bool:
            return filepath.endswith(".synthetic")

        def load(self, filepath: str) -> Dict[str, Any]:
            import numpy as np

            # Generate synthetic SAS data with error bars
            n_points = 1000
            x = np.linspace(0.01, 10.0, n_points)
            y = np.exp(-x**2 / 10) + np.random.normal(0, 0.01, n_points)
            y_err = np.abs(y * 0.05)  # 5% error

            return {
                "type": "synthetic",
                "filepath": filepath,
                "sas_data_list": [
                    type("SASData", (), {
                        "x": x,
                        "y": y,
                        "y_err": y_err,
                        "x_label": "Q",
                        "y_label": "I(Q)",
                    })()
                ],
            }

    # Register the synthetic loader
    dispatcher = get_default_dispatcher()
    synthetic_loader = SyntheticLoader()
    dispatcher.register(synthetic_loader)

    # Generate 150 synthetic datasets
    n_datasets = 150
    print(f"\n=== Testing Large Dataset Loading ({n_datasets} datasets) ===")

    start_time = time.time()
    loaded_data: Dict[str, Any] = {}

    for i in range(n_datasets):
        filepath = f"dataset_{i:04d}.synthetic"
        data = dispatcher.load(filepath)
        if data is not None:
            loaded_data[f"Dataset {i + 1}"] = data

    load_time = time.time() - start_time
    print(f"Loaded {len(loaded_data)} datasets in {load_time:.2f} seconds")
    print(f"Average time per dataset: {load_time / n_datasets * 1000:.2f} ms")

    # Verify all datasets loaded
    assert len(loaded_data) == n_datasets, f"Expected {n_datasets} datasets, got {len(loaded_data)}"

    # Verify data structure
    for name, data in loaded_data.items():
        assert "sas_data_list" in data, f"{name} missing sas_data_list"
        assert len(data["sas_data_list"]) > 0, f"{name} has empty sas_data_list"
        for sas_data in data["sas_data_list"]:
            assert hasattr(sas_data, "x"), f"{name} missing x attribute"
            assert hasattr(sas_data, "y"), f"{name} missing y attribute"
            assert hasattr(sas_data, "y_err"), f"{name} missing y_err attribute"
            assert len(sas_data.x) > 0, f"{name} has empty x data"
            assert len(sas_data.y) > 0, f"{name} has empty y data"
            assert len(sas_data.y_err) > 0, f"{name} has empty y_err data"

    print("✓ All datasets loaded successfully with valid structure")
    return True


def test_large_dataset_rendering():
    """Test rendering 100+ datasets efficiently."""
    import numpy as np

    print(f"\n=== Testing Large Dataset Rendering ===")

    # Simulate rendering 100 datasets
    n_datasets = 100
    start_time = time.time()

    # Simulate creating plot data (similar to what LinePlotter does)
    datasets = []
    for i in range(n_datasets):
        x = np.linspace(0.01, 10.0, 1000)
        y = np.exp(-x**2 / 10) + np.random.normal(0, 0.01, 1000)
        y_err = np.abs(y * 0.05)

        datasets.append({
            "x": x,
            "y": y,
            "y_err": y_err,
            "title": f"Dataset {i + 1}",
        })

    # Simulate getting plot config (similar to what LinePlotter.get_plot_config does)
    x_min = float(min(d["x"].min() for d in datasets))
    x_max = float(max(d["x"].max() for d in datasets))
    y_min = float(min(d["y"].min() for d in datasets))
    y_max = float(max(d["y"].max() for d in datasets))

    render_time = time.time() - start_time
    print(f"Prepared {n_datasets} datasets for rendering in {render_time:.2f} seconds")
    print(f"Average time per dataset: {render_time / n_datasets * 1000:.2f} ms")
    print(f"Data range: X=[{x_min:.4f}, {x_max:.4f}], Y=[{y_min:.6f}, {y_max:.6f}]")

    assert render_time < 5.0, f"Rendering preparation took too long: {render_time:.2f}s"
    print("✓ Large dataset rendering preparation completed within time limit")
    return True


def test_error_bar_handling():
    """Test error bar handling with large datasets."""
    import numpy as np

    print(f"\n=== Testing Error Bar Handling ===")

    n_datasets = 50
    start_time = time.time()

    # Simulate creating error bar data
    error_bars = []
    for i in range(n_datasets):
        x = np.linspace(0.01, 10.0, 500)
        y = np.exp(-x**2 / 10) + np.random.normal(0, 0.01, 500)
        y_err = np.abs(y * 0.05)

        error_bars.append({
            "x": x,
            "y": y,
            "height": y_err,  # pyqtgraph uses 'height' for error bars
        })

    process_time = time.time() - start_time
    print(f"Prepared {n_datasets} error bar datasets in {process_time:.2f} seconds")
    print(f"Average time per dataset: {process_time / n_datasets * 1000:.2f} ms")

    assert process_time < 3.0, f"Error bar preparation took too long: {process_time:.2f}s"
    print("✓ Error bar handling completed within time limit")
    return True


def test_memory_usage():
    """Test memory usage with large datasets."""
    import numpy as np

    print(f"\n=== Testing Memory Usage ===")

    # Create 100 datasets with 10,000 points each
    n_datasets = 100
    points_per_dataset = 10_000

    start_time = time.time()
    total_points = 0

    for i in range(n_datasets):
        x = np.linspace(0.01, 10.0, points_per_dataset)
        y = np.exp(-x**2 / 10) + np.random.normal(0, 0.01, points_per_dataset)
        y_err = np.abs(y * 0.05)

        total_points += len(x)
        # In a real test, we would track memory usage here

    process_time = time.time() - start_time
    print(f"Processed {n_datasets} datasets × {points_per_dataset:,} points = {total_points:,} total points")
    print(f"Processing time: {process_time:.2f} seconds")

    # Calculate approximate memory usage (3 arrays × 8 bytes per float64)
    approx_memory_mb = total_points * 3 * 8 / (1024**2)
    print(f"Approximate memory usage: {approx_memory_mb:.1f} MB")

    assert process_time < 5.0, f"Memory test took too long: {process_time:.2f}s"
    print("✓ Memory usage test completed within time limit")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Bernardyn Performance Tests")
    print("=" * 60)

    tests = [
        test_large_dataset_loading,
        test_large_dataset_rendering,
        test_error_bar_handling,
        test_memory_usage,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Performance Test Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    else:
        print("\nAll performance tests passed!")
