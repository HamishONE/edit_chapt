import contextlib
import os
import subprocess
import sys

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
EDITOR = os.getenv("EDITOR", "vim")
AUTOMATIC_CHAPTER = "Intro"
TIMEBASE = 1000


def get_duration(file):
	cmd = FFPROBE + ' -i {} -show_entries format=duration -v quiet -of csv="p=0"'.format(file)
	output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
	return int(float(output))


def int_to_str(int_in):
	secs = int_in % 60
	minutes = int_in // 60
	return f"{minutes}:{secs:02d}"


def str_to_int(str_in):
	parts = str_in.split(":")
	return int(parts[0])*60 + int(parts[1])


# Check for command line argument
if len(sys.argv) != 2:
	print("USAGE: python edit_chapt.py VIDEO")
	exit()

# Setup temporary file names
input_name = sys.argv[1]
input_name_only, input_extension = os.path.splitext(input_name)
input_meta_name = input_name + "_meta_in.ini"
our_display_name = input_name + "_meta_display"
output_meta_name = input_name + "_meta_out.ini"
output_name = input_name_only + "_tmp_out" + input_extension

try:
	chapters = []
	new_chapters = []
	max_length = get_duration(input_name)

	# Extract current metadata
	extract_meta_args = [FFMPEG, '-y', '-i', input_name, '-f', 'ffmetadata', input_meta_name]
	subprocess.check_output(extract_meta_args, stderr=subprocess.DEVNULL)
	with open(input_meta_name) as input_meta:
		temp_chapter = None
		for line in input_meta.readlines():
			line = line.strip()
			if line == "[CHAPTER]":
				if temp_chapter is not None:
					chapters.append(temp_chapter)
				temp_chapter = {}
			elif temp_chapter is None:
				continue
			elif line.startswith("TIMEBASE"):
				temp_chapter["TIMEBASE"] = int(line.replace("TIMEBASE=1/", ""))
			elif line.startswith("START"):
				temp_chapter["START"] = int(line.replace("START=", ""))
			elif line.startswith("END"):
				temp_chapter["END"] = int(line.replace("END=", ""))
			elif line.startswith("title"):
				temp_chapter["title"] = line.replace("title=", "")

	if temp_chapter is not None:
		chapters.append(temp_chapter)

	if AUTOMATIC_CHAPTER and len(chapters) == 0:
		chapters.append({
			"TIMEBASE": TIMEBASE,
			"START": 0,
			"END": max_length * TIMEBASE,
			"title": "Intro"
		})

	# Allow the user to edit a more readable file
	with open(our_display_name, "w+") as our_display:
		# Generate the display file
		for chapter in chapters:
			start = int_to_str(chapter["START"]//chapter["TIMEBASE"])
			end = int_to_str(chapter["END"]//chapter["TIMEBASE"])
			our_display.write(f"{chapter['title']} {start}\n")
		our_display.flush()

		# Let the user edit with vim
		subprocess.call([EDITOR, our_display_name])
		our_display.seek(0)

		# Parse back what the user has made
		for line in our_display.readlines():
			line = line.strip()
			if line == "":
				continue

			name, start = line.split(" ")
			new_chapters.append({
				"START": str_to_int(start),
				"title": name
			})

	# Write back new meta file
	with open(output_meta_name, "w") as output_meta:
		output_meta.write(";FFMETADATA1\n\n")
		for index, chapter in enumerate(new_chapters):
			if index + 1 == len(new_chapters):
				end = max_length
			else:
				next_chapter = new_chapters[index + 1]
				end = next_chapter["START"]

			if chapter['START'] > max_length:
				wanted = int_to_str(chapter['START'])
				limit = int_to_str(max_length)
				raise Exception(f"Chapter cannot start at {wanted}, the video is only {limit} long")

			output_meta.write("[CHAPTER]\n")
			output_meta.write(f"TIMEBASE=1/{TIMEBASE}\n")
			output_meta.write(f"START={chapter['START'] * TIMEBASE}\n")
			output_meta.write(f"END={end * TIMEBASE}\n")
			output_meta.write(f"title={chapter['title']}\n")

	# Create a new video file with the metadata
	run_args = [FFMPEG, '-y', '-i', input_name, '-i', output_meta_name,
				'-map_metadata', '1', '-map_chapters', '1', '-codec', 'copy', output_name]
	subprocess.check_output(run_args, stderr=subprocess.DEVNULL)

	# Rename the files
	os.replace(input_name, input_name + ".old")
	os.rename(output_name, input_name)
	print("New chapter metadata written to " + input_name)

finally:
	# Remove temporary files
	with contextlib.suppress(FileNotFoundError):
		os.remove(input_meta_name)
		os.remove(our_display_name)
		os.remove(output_meta_name)
		os.remove(output_name)
