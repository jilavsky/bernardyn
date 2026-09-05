from bernardyn.state import UserState


def test_user_state_round_trips_without_touching_graph_packages(tmp_path):
    path = tmp_path / ".bernardyn" / "state.json"
    state = UserState(path)
    state.set("last_data_folder", "/data/example")
    state.set("data_selector", {"sort_index": 6, "dataset_profiles": {"layout": [1]}})
    state.save()
    restored = UserState(path)
    assert restored.get("last_data_folder") == "/data/example"
    assert restored.get("data_selector")["dataset_profiles"] == {"layout": [1]}
