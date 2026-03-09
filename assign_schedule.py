import datetime
import random
import pandas as pd

import google_utils as gu
from config import DAY_MAP, get_presenter_cols

seed = 0
random.seed(seed)


def get_next_n_days(start_date, day_name, n=16):
    """Return a list of the next n occurrences of day_name starting from start_date."""
    target = DAY_MAP[day_name.lower()]
    dates = []
    current_date = start_date
    while current_date.weekday() != target:
        current_date += datetime.timedelta(days=1)
    for _ in range(n):
        dates.append(current_date.strftime("%Y-%m-%d"))
        current_date += datetime.timedelta(days=7)
    return dates


def assign_roles(
    schedule_df,
    names,
    presenter_cols,
    min_presenter_gap=4,
    presentation_weight=4,
):
    usage_count = {name: 0 for name in names}
    last_presented = {name: -min_presenter_gap for name in names}
    n_weeks = len(schedule_df)
    future_assignments = {week: [] for week in range(n_weeks)}

    schedule_df["Date"] = pd.to_datetime(schedule_df["Date"])

    today = datetime.date.today()
    five_months_ago = today - datetime.timedelta(days=150)

    # First pass: Prepopulate future assignments with existing presenters
    for week_index, row in schedule_df.iterrows():
        for col in presenter_cols:
            presenter = row[col]
            presenter_clean = presenter.replace("[P] ", "")
            if presenter_clean != "EMPTY":
                for future_week in range(
                    week_index + 1, min(week_index + min_presenter_gap, n_weeks)
                ):
                    future_assignments[future_week].append(presenter_clean)

    # Second pass: Fill empty slots
    for week_index, row in schedule_df.iterrows():
        presentation_date = row["Date"].date()
        presenters = [row[col] for col in presenter_cols]

        for i in range(len(presenter_cols)):
            if presenters[i] == "EMPTY":
                additional_presenter = pick_presenters(
                    names,
                    usage_count,
                    last_presented,
                    future_assignments,
                    week_index,
                    min_presenter_gap,
                    presentation_weight,
                    n_weeks,
                    number=1,
                )[0]
                presenters[i] = f"[P] {additional_presenter}"

                if presentation_date >= five_months_ago:
                    usage_count[additional_presenter] += 1
                last_presented[additional_presenter] = week_index

                for future_week in range(
                    week_index + 1, min(week_index + min_presenter_gap, n_weeks)
                ):
                    future_assignments[future_week].append(additional_presenter)
            else:
                presenter_clean = presenters[i].replace("[P] ", "")
                if presenter_clean in names:
                    if presentation_date >= five_months_ago:
                        usage_count[presenter_clean] += 1
                    last_presented[presenter_clean] = week_index

        for i, col in enumerate(presenter_cols):
            schedule_df.at[week_index, col] = presenters[i]

    return schedule_df


def pick_presenters(
    names,
    usage_count,
    last_presented,
    future_assignments,
    current_week,
    min_presenter_gap,
    presentation_weight,
    n_weeks,
    number=1,
):
    candidates = []

    for name in names:
        recently_presented = current_week - last_presented[name] < min_presenter_gap
        upcoming_presentation = any(
            name in future_assignments[week]
            for week in range(
                current_week + 1, min(current_week + min_presenter_gap, n_weeks)
            )
        )

        if not recently_presented and not upcoming_presentation:
            candidates.append((name, usage_count[name]))

    if len(candidates) < number:
        candidates = [
            (name, usage_count[name])
            for name in names
            if current_week - last_presented[name] >= min_presenter_gap
        ]

    random.shuffle(candidates)
    candidates.sort(key=lambda x: x[1] * presentation_weight)

    return [candidate[0] for candidate in candidates[:number]]


def fill_empty_slots(group_slug, group_config, seed=None):
    if seed is not None:
        random.seed(seed)

    names_dict = gu.get_participants_list(group_slug)
    names = [n["Name"] for n in names_dict]

    schedule_df = gu.get_schedule_df(group_slug)
    presenter_cols = get_presenter_cols(group_config)

    updated_schedule_df = assign_roles(
        schedule_df,
        names,
        presenter_cols,
        min_presenter_gap=7,
        presentation_weight=1,
    )

    return updated_schedule_df


if __name__ == "__main__":
    seed = 0
    # Requires group_slug and group_config to be passed
    print("Run via the app interface.")
