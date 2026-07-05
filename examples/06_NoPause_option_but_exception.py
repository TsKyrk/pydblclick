# Don't pause this script in console (unless there is an exception):
pydblclick_customizations['must_pause_in_console'] = False

print("hello world")
print(1 / 0)  # the exception overrides the no-pause option: traceback stays visible
