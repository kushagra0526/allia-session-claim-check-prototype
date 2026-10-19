import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

r = json.load(open("out/heldout_first_run.json"))
res, kinds = r["results"], sorted(r["defects_by_kind"])
names = {"claim": "claim scrubber", "note": "note-trusting check", "full": "note + recording (this)"}
fig, ax = plt.subplots(figsize=(13, 5))
w = 0.27
for j, m in enumerate(names):
    ax.barh([i + (j - 1) * w for i in range(len(kinds))],
            [res[m]["per_defect"].get(k, 0) / r["defects_by_kind"][k] * 100 for k in kinds], w,
            label=names[m], color=["#bbb", "#888", "#2a7"][j])
ax.set_yticks(range(len(kinds)))
ax.set_yticklabels([k.replace("_", " ") for k in kinds])
ax.invert_yaxis()
ax.set_xlabel("% of planted defects caught for the right reason")
ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0))
f = res["full"]
ax.set_title(f"Held-out, first run: {f['caught']}/{f['defects']} caught, {f['clean_stopped']}/{f['clean']} clean sessions wrongly stopped")
fig.tight_layout()
fig.savefig("docs/result.png", dpi=110)
