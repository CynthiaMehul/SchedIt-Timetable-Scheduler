import re
import json
import random
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest
from django.http import JsonResponse

def check_session(request):
    courses = request.session.get("courses")
    return JsonResponse({"courses_loaded": bool(courses)})

# -------------------
# Parser regex
# -------------------
slot_pattern = re.compile(r"(BLENDED|[0-9A-Z]+-[0-9]+),([A-Z]+)-(.+)")
day_pattern = re.compile(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday):\s*(.+)")

def parse_raw_text(raw_text):
    courses = {}
    lines = raw_text.split("\n")
    i = 0
    current_course = None

    while i < len(lines):
        line = lines[i].strip()

        # Course code + credits
        course_match = re.match(r"([0-9A-Z]+)\s+\[(\d+)\s+Credits\]", line)
        if course_match:
            code = course_match.group(1)
            credits = int(course_match.group(2))
            courses[code] = {"name": "", "credits": credits, "slots": []}
            current_course = code
            i += 1
            continue

        # Course name after "Course overview"
        if line == "Course overview":
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            if j < len(lines) and current_course:
                courses[current_course]["name"] = lines[j].strip()
            i += 1
            continue

        # Slot + faculty
        slot_match = slot_pattern.match(line)
        if slot_match and current_course:
            slot_name = slot_match.group(1)
            faculty = slot_match.group(3).strip()

            # Ignore dummy PHASE-I slots
            if "PHASE-I" in faculty or faculty.strip() == "":
                i += 1
                continue

            slot_obj = {"slot_name": slot_name, "faculty": faculty, "days": {}}

            k = i + 1
            while k < len(lines):
                next_line = lines[k].strip()
                if slot_pattern.match(next_line) or re.match(r"[0-9A-Z]+\s+\[\d+ Credits\]", next_line):
                    break
                day_match = day_pattern.match(next_line)
                if day_match:
                    day = day_match.group(1)
                    times_raw = day_match.group(2)
                    times = re.findall(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}", times_raw)
                    if times:
                        slot_obj["days"][day] = times
                k += 1

            if slot_obj["days"]:
                courses[current_course]["slots"].append(slot_obj)
            i = k
            continue

        i += 1

    # Remove empty slots
    for c in list(courses.keys()):
        courses[c]["slots"] = [s for s in courses[c]["slots"] if s["days"]]

    return courses

# -------------------
# Views
# -------------------
def home(request):
    return render(request, "myapp/home.html")

def instructions(request):
    return render(request, "myapp/instructions.html")

@csrf_exempt
def upload_raw_text(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    try:
        data = json.loads(request.body)
        raw_text = data.get("raw_text", "")
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    courses = parse_raw_text(raw_text)
    request.session['courses'] = courses
    request.session.modified = True  # ensure session saves

    summary = {code: {"name": courses[code].get("name",""), 
                      "credits": courses[code]["credits"], 
                      "slots": len(courses[code]["slots"])} 
               for code in courses}

    return JsonResponse({"status": "ok", "count": len(courses), "summary": summary})

def edit_courses(request):
    # ✅ NEW: Clear ONLY when extension starts fresh (keeps sessionStorage flow intact)
    if request.GET.get("new") == "1":
        request.session.pop('selected_codes', None)
        request.session.pop('fixed_slots', None)
        request.session.pop('last_timetable', None)
        request.session.modified = True
    
    courses = request.session.get('courses', {})
    if not courses:
        return render(request, "myapp/upload.html", {"error": "Courses not loaded. Use the extension to upload raw text."})

    if request.method == "POST":
        selected_codes = request.POST.getlist("selected_courses")
        total_credits = sum(courses[code]["credits"] for code in selected_codes)
        if total_credits > 30:
            return render(request, "myapp/edit.html", {"courses": courses, "error": "Selected credits exceed 30. Please reduce."})

        fixed_slots = {}
        for code in selected_codes:
            slot_index = request.POST.get(f"slot_{code}")
            if slot_index is not None and slot_index != "":
                try:
                    idx = int(slot_index)
                    fixed_slots[code] = courses[code]['slots'][idx]
                except Exception:
                    pass

        # ✅ CRITICAL: Store in BOTH sessionStorage AND Django session
        request.session['selected_codes'] = selected_codes
        request.session['fixed_slots'] = fixed_slots
        request.session.modified = True
        
        # ✅ NEW: Also save to sessionStorage for persistence during navigation
        if 'selected_codes' in request.session:
            # This runs client-side JS (see edit.html changes)
            pass

        return redirect("myapp:generate")

    return render(request, "myapp/edit.html", {"courses": courses})

def timetable_view(request):
    result = request.session.get("last_timetable", {})
    return render(request, "myapp/timetable.html", result)

# -------------------
# GA Generate function
# -------------------
def generate(request):
    courses = request.session.get('courses', {})
    if not courses:
        return render(request, 'myapp/upload.html', {'error': 'Courses not loaded.'})

    selected_codes = request.session.get('selected_codes', [])
    fixed_slots = request.session.get('fixed_slots', {})

    if not selected_codes:
        return redirect("myapp:edit_courses")

    population_size = 50
    generations = 200
    crossover_rate = 0.8
    mutation_rate = 0.2

    def create_individual():
        individual = []
        for code in selected_codes:
            if code in fixed_slots:
                individual.append(fixed_slots[code])
            else:
                slots = courses[code]['slots']
                if not slots:
                    individual.append({"slot_name": "NONE", "faculty": "", "days": {}})
                else:
                    individual.append(random.choice(slots))
        return individual

    def evaluate(individual):
        schedule = {}
        fitness = 100.0
        for slot in individual:
            for day, timings in slot.get('days', {}).items():
                if day not in schedule:
                    schedule[day] = set()
                for time in timings:
                    if time in schedule[day]:
                        fitness -= 10
                    schedule[day].add(time)
        return fitness

    def tournament_selection(pop, k=3):
        selected = random.sample(pop, k)
        selected.sort(key=evaluate, reverse=True)
        return selected[0]

    def crossover(p1, p2):
        if len(p1) < 2 or random.random() > crossover_rate:
            return p1.copy(), p2.copy()
        point = random.randint(1, len(p1)-1)
        c1 = p1[:point] + p2[point:]
        c2 = p2[:point] + p1[point:]
        for i, code in enumerate(selected_codes):
            if code in fixed_slots:
                c1[i] = fixed_slots[code]
                c2[i] = fixed_slots[code]
        return c1, c2

    def mutate(individual):
        for i, code in enumerate(selected_codes):
            if code in fixed_slots:
                continue
            if random.random() < mutation_rate and courses[code]['slots']:
                individual[i] = random.choice(courses[code]['slots'])
        return individual

    population = [create_individual() for _ in range(population_size)]
    for gen in range(generations):
        new_pop = []
        population.sort(key=evaluate, reverse=True)
        new_pop.append(population[0])
        while len(new_pop) < population_size:
            p1 = tournament_selection(population)
            p2 = tournament_selection(population)
            c1, c2 = crossover(p1, p2)
            c1 = mutate(c1)
            c2 = mutate(c2)
            new_pop.extend([c1, c2])
        population = new_pop[:population_size]

    best = max(population, key=evaluate)

    # Optimize final schedule
    final_schedule = {}
    selected_without_clash = []
    skipped_courses = []

    for i, code in enumerate(selected_codes):
        slot = best[i]
        fits = True
        for day, timings in slot.get('days', {}).items():
            if any(time in final_schedule.setdefault(day, set()) for time in timings):
                fits = False
                break
        if fits:
            selected_without_clash.append((code, slot))
            for day, timings in slot.get('days', {}).items():
                final_schedule[day].update(timings)
        else:
            skipped_courses.append((code, courses[code]['name'], slot.get('slot_name', '')))

    all_hours = [
        '08:00 - 09:00','09:00 - 10:00','10:00 - 11:00','11:00 - 12:00',
        '12:00 - 13:00','13:00 - 14:00','14:00 - 15:00','15:00 - 16:00',
        '16:00 - 17:00'
    ]
    all_days = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday']

    schedule_dict = {day: {hour: "" for hour in all_hours} for day in all_days}
    for code, slot in selected_without_clash:
        for day, timings in slot.get('days', {}).items():
            for time in timings:
                if time in schedule_dict[day]:
                    schedule_dict[day][time] = code

    schedule_list = []
    for day in all_days:
        schedule_list.append([schedule_dict[day].get(hour, "-") for hour in all_hours])

    context = {
        'hours': all_hours,
        'days_schedule': list(zip(all_days, schedule_list)),
        'skipped_courses': skipped_courses
    }

    request.session['last_timetable'] = context
    return render(request, 'myapp/timetable.html', context)
