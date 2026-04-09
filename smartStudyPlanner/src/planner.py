def generate_schedule(subjects, time_slots, study_minutes=25, break_minutes=5):
    schedule = []

    study_block = max(5, int(study_minutes)) / 60
    break_block = max(0, int(break_minutes)) / 60

    filtered_subjects = []
    for sub in subjects:
        name = sub.get("name", "").strip()
        topics = max(0, int(sub.get("topics", 0)))

        if not name or topics == 0:
            continue

        filtered_subjects.append({"name": name, "topics": topics})

    # Build queue in round-robin order so all subjects get scheduled fairly.
    topic_queue = []
    while True:
        added_any = False
        for sub in filtered_subjects:
            if sub["topics"] > 0:
                topic_queue.append(sub["name"])
                sub["topics"] -= 1
                added_any = True
        if not added_any:
            break

    if not topic_queue:
        return schedule

    next_topic = 0
    revision_index = 0

    for start, end in time_slots:
        current_time = start

        while current_time + study_block <= end:
            if next_topic < len(topic_queue):
                selected_subject = topic_queue[next_topic]
                next_topic += 1
            else:
                # Continue with cyclic revision sessions so all available free time can be used.
                selected_subject = filtered_subjects[revision_index % len(filtered_subjects)]["name"]
                revision_index += 1

            if current_time + study_block > end:
                break

            schedule.append({
                "type": "study",
                "subject": selected_subject,
                "start": current_time,
                "end": current_time + study_block
            })
            current_time += study_block

            has_future_session = current_time + break_block + study_block <= end
            if has_future_session and break_block > 0:
                    schedule.append({
                        "type": "break",
                        "subject": "Break",
                        "start": current_time,
                        "end": current_time + break_block
                    })
                    current_time += break_block

    return schedule


def format_time(t):
    total_minutes = round(t * 60)
    total_minutes = total_minutes % (24 * 60)

    hours = total_minutes // 60
    minutes = total_minutes % 60

    suffix = "AM"
    if hours >= 12:
        suffix = "PM"
    if hours > 12:
        hours -= 12
    if hours == 0:
        hours = 12

    return f"{hours}:{minutes:02d} {suffix}"