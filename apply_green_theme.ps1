$file = "web\index.html"
$content = Get-Content $file -Raw -Encoding UTF8

# ---- BACKGROUND COLORS ----
# Dark navy -> Dark green-black
$content = $content -replace '#0A0F1D', '#051209'
$content = $content -replace '#0F172A', '#071A0D'
$content = $content -replace '#0E1526', '#071A0D'
$content = $content -replace '#111827', '#0D2116'
$content = $content -replace '#1F2937', '#163A22'
$content = $content -replace '#374151', '#1E5230'

# ---- CARD BORDERS ----
$content = $content -replace 'border-slate-800', 'border-emerald-900'
$content = $content -replace 'border-slate-700', 'border-emerald-800'
$content = $content -replace 'bg-slate-950', 'bg-green-950'
$content = $content -replace 'bg-slate-900', 'bg-green-900/60'
$content = $content -replace 'bg-slate-800', 'bg-green-800'

# ---- GRADIENT HEADER / BRAND ----
$content = $content -replace 'from-blue-600 via-indigo-600 to-cyan-400', 'from-emerald-600 via-green-600 to-teal-400'
$content = $content -replace 'from-blue-600 to-cyan-400', 'from-emerald-600 to-teal-400'

# ---- ACCENT BLUE -> EMERALD/GREEN ----
$content = $content -replace 'blue-600', 'emerald-600'
$content = $content -replace 'blue-500', 'emerald-500'
$content = $content -replace 'blue-400', 'emerald-400'
$content = $content -replace 'indigo-600', 'green-600'
$content = $content -replace 'indigo-950', 'green-950'

# ---- CYAN -> TEAL ----
$content = $content -replace 'cyan-600', 'teal-600'
$content = $content -replace 'cyan-500', 'teal-500'
$content = $content -replace 'cyan-400', 'teal-400'
$content = $content -replace 'cyan-300', 'teal-300'

# ---- PURPLE -> KEEP AS IS (checkpoints have their own distinct colors) ----
# Purple checkpoint icon stays, adds contrast

# ---- SELECTION HIGHLIGHT ----
$content = $content -replace 'selection:bg-blue-600', 'selection:bg-emerald-600'

# ---- GUIDE CHAT button gradient ----
$content = $content -replace 'from-blue-600 via-indigo-600 to-cyan-500', 'from-emerald-600 via-green-600 to-teal-500'
$content = $content -replace 'hover:from-blue-500 hover:to-cyan-400', 'hover:from-emerald-500 hover:to-teal-400'

# ---- GUIDE HEADER gradient ----
$content = $content -replace 'via-indigo-950/60', 'via-green-950/60'

# ---- SEND BUTTON blue -> green ----
# (already handled above via blue-600 -> emerald-600)

# ---- CSS scrollbar thumb ----
$content = $content -replace "background: #374151;", "background: #1E5230;"

# ---- flashGreen/flashRed keyframes border reset -> green tones ----
$content = $content -replace "border-color: #1F2937; background-color: #111827;", "border-color: #163A22; background-color: #0D2116;"

# Write back
Set-Content $file $content -Encoding UTF8
Write-Host "Theme applied successfully!"
