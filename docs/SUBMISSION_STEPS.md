# Submission steps

1. **Push to GitHub** (create an empty **public** repo named `finn` on github.com first), then from the unzipped `finn` folder:
   ```bash
   git init && git add . && git commit -m "FINN: ENAM AI Engineer Build Challenge"
   git branch -M main
   git remote add origin https://github.com/<your-username>/finn.git
   git push -u origin main
   ```
2. **Host on Vercel:** vercel.com/new → import the repo → Deploy (`vercel.json` handles the settings). Copy the URL.
3. **Share links:** in claude.ai, open each FINN chat → **Share** → copy the link. Paste them into `ai-build-history/README.md`, then commit and push again.
4. **Email:** paste `docs/COVERING_EMAIL.md` into your mail, fill in the GitHub and Vercel URLs, and send it to assessment@enam.com with the subject **ENAM - IIT screening - 2027**.
