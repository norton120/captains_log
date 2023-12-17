![Captain's Log](https://external-preview.redd.it/c8RX25m4_6FOhebqxP5ga5nR77wIpdPJV3fIO6t0xiI.jpg?auto=webp&s=fbd2b4720d2c2c5fd4224bf819797be6c82c2e95)

Daily journaling has plenty of benefits. But if you already
spend 10 hours a day on a screen, the idea of sitting down to log _more_ time with your, eh, daily log, is not exciting.

Enter Captain's log.

1. Record your daily log as an audio file (iPhone recorder works great).
2. Drop the file into your designated audio_files folder
3. Run `captains-log process`
4. You now have the log written and readable in the designated markdown_files folder
5. You also have semantic embeddings for your log, complete
with the original audio file and timestamps

Now you can do a similarity search using `captains-log search "I think I drink too much"` and the top _k_ similar audio logs will open up in browser windows, right to the related point in the log. So this might open up the part of your New Year's log where you talk about dry January, or the log last September when you decided you needed to switch back to only wine.
`captains-log summary week` gives you a summary of your last week. also accepts `day`, `month`, `quarter`