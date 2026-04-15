
# planner.py (restored for deployment compatibility)
from datetime import datetime, timedelta

def generate_schedule(subjects, start_time, end_time, session_length=50, break_length=10):
	"""
	Generate a simple study schedule given subjects, start/end times, and session/break lengths.
	Returns a list of dicts with session info.
	"""
	schedule = []
	current_time = datetime.strptime(start_time, "%H:%M")
	end_time_dt = datetime.strptime(end_time, "%H:%M")
	subject_idx = 0
	while current_time + timedelta(minutes=session_length) <= end_time_dt:
		subject = subjects[subject_idx % len(subjects)]
		session = {
			"subject": subject,
			"start": current_time.strftime("%H:%M"),
			"end": (current_time + timedelta(minutes=session_length)).strftime("%H:%M"),
			"type": "study"
		}
		schedule.append(session)
		current_time += timedelta(minutes=session_length)
		# Add break if there's still time
		if current_time + timedelta(minutes=break_length) <= end_time_dt:
			break_session = {
				"subject": "Break",
				"start": current_time.strftime("%H:%M"),
				"end": (current_time + timedelta(minutes=break_length)).strftime("%H:%M"),
				"type": "break"
			}
			schedule.append(break_session)
			current_time += timedelta(minutes=break_length)
		subject_idx += 1
	return schedule

def format_time(dt):
	"""
	Format a datetime object as HH:MM string.
	"""
	return dt.strftime("%H:%M")
