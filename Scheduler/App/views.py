from django.shortcuts import render
import re
import random

def home(request):
    return render(request, 'App/home.html')

def upload(request):
    return render(request, 'App/upload.html')

def parser(request):
    if request.method == 'POST':
        user_text = request.POST.get('content')  # get pasted content
        courses={}
        lines = [line.strip() for line in user_text.splitlines() if line.strip()]

        course_code = ""
        course_name = ""
        credits = 0
        slot_name = ""
        faculty = ""
        slots = []
        current_slot_days = {}

        i = 0
        while i < len(lines):
            line = lines[i]

            # Course code and credits
            m = re.match(r"([0-9A-Z]+) \[(\d+) Credits\]", line)
            if m:
                # Save previous course
                if course_code and slots:
                    courses[course_code] = {
                        "name": course_name,
                        "credits": credits,
                        "slots": slots
                    }
                course_code = m.group(1)
                credits = int(m.group(2))
                slots = []
                i += 1
                continue

            # Course name
            if line == "Course overview" and i + 1 < len(lines):
                course_name = lines[i + 1]
                i += 2
                continue

            # Skip PHASE-I lines completely
            if "PHASE-I" in line:
                i += 1
                continue

            # Slot + faculty line
            if re.match(r".*, .* - .*", line):
                slot_name = line.split(",")[0].strip()
                faculty = line.split("-")[-1].strip()  # only the actual faculty name
                current_slot_days = {}
                i += 1
                # Parse following day/time lines for this slot
                while i < len(lines) and not re.match(r"[0-9A-Z]+ \[\d+ Credits\]", lines[i]) \
                        and "PHASE-I" not in lines[i] \
                        and not re.match(r".*, .* - .*", lines[i]):
                    day_match = re.match(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday):\s*(.+)", lines[i])
                    if day_match:
                        day = day_match.group(1)
                        times_line = day_match.group(2)
                        # Allow optional spaces around dash and squished times
                        times = re.findall(r"\d{2}:\d{2}\s*-\s*\d{2}:\d{2}", times_line)
                        if times:
                            current_slot_days[day] = times
                    i += 1
                # Save this slot if it has any days
                if current_slot_days:
                    slots.append({
                        "slot_name": slot_name,
                        "faculty": faculty,
                        "days": current_slot_days
                    })
                continue

            i += 1

        # Save last course
        if course_code and slots:
            courses[course_code] = {
                "name": course_name,
                "credits": credits,
                "slots": slots
            }
        request.session['courses'] = courses
        # Pass processed result to a new template
        return render(request, 'App/select.html', {'courses': courses})

    # If GET request, show the upload page
    return render(request, 'App/upload.html')

def generate(request):
    courses = request.session.get('courses', {})
    if not courses:
        return render(request, 'App/upload.html', {'error': 'Courses not loaded.'})

    if request.method == 'POST':
        # --- 1. Retrieve selected courses and slots ---
        selected_codes = request.POST.getlist('selected_courses')
        fixed_slots = {}
        for code in selected_codes:
            slot_index = request.POST.get(f'slot_{code}')
            if slot_index is not None:
                fixed_slots[code] = courses[code]['slots'][int(slot_index)]

        # --- 2. GA parameters ---
        population_size = 50
        generations = 200
        crossover_rate = 0.8
        mutation_rate = 0.2

        # --- 3. GA helper functions ---
        def create_individual():
            individual = []
            for code in selected_codes:
                if code in fixed_slots:
                    individual.append(fixed_slots[code])
                else:
                    slots = courses[code]['slots']
                    individual.append(random.choice(slots))
            return individual

        def evaluate(individual):
            schedule = {}
            fitness = 100
            for slot in individual:
                for day, timings in slot['days'].items():
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
                if random.random() < mutation_rate:
                    individual[i] = random.choice(courses[code]['slots'])
            return individual

        # --- 4. Initialize population and run GA ---
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

        # --- 5. Optimize final schedule ---
        def optimize_best(best, selected_codes, fixed_slots, all_courses):
            final_schedule = {}
            selected_without_clash = []
            skipped_courses = []

            for i, code in enumerate(selected_codes):
                slot = best[i]
                # fixed slots first
                if code in fixed_slots:
                    selected_without_clash.append((code, slot))
                    for day, timings in slot['days'].items():
                        final_schedule.setdefault(day, set()).update(timings)
                    continue

                # try GA choice first
                fits = True
                for day, timings in slot['days'].items():
                    if any(time in final_schedule.setdefault(day, set()) for time in timings):
                        fits = False
                        break

                if fits:
                    selected_without_clash.append((code, slot))
                    for day, timings in slot['days'].items():
                        final_schedule[day].update(timings)
                else:
                    # try other slots
                    placed = False
                    for alt_slot in all_courses[code]['slots']:
                        fits_alt = True
                        for day, timings in alt_slot['days'].items():
                            if any(time in final_schedule.setdefault(day, set()) for time in timings):
                                fits_alt = False
                                break
                        if fits_alt:
                            selected_without_clash.append((code, alt_slot))
                            for day, timings in alt_slot['days'].items():
                                final_schedule[day].update(timings)
                            placed = True
                            break
                    if not placed:
                        skipped_courses.append((code, all_courses[code]['name'], slot['slot_name']))

            return selected_without_clash, skipped_courses, final_schedule

        selected_without_clash, skipped_courses, final_schedule = optimize_best(
            best, selected_codes, fixed_slots, courses
        )

        # --- 6. Prepare table for HTML rendering ---
        all_hours = [
            '08:00 - 09:00','09:00 - 10:00','10:00 - 11:00','11:00 - 12:00',
            '12:00 - 13:00','13:00 - 14:00','14:00 - 15:00','15:00 - 16:00',
            '16:00 - 17:00'
        ]
        all_days = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday']

        # build dict day -> hour -> course code
        schedule_dict = {day: {hour: "" for hour in all_hours} for day in all_days}
        for code, slot in selected_without_clash:
            for day, timings in slot['days'].items():
                for time in timings:
                    schedule_dict[day][time] = code  # can also include slot_name if desired

        # --- 7. Render timetable.html ---
        # build list of courses per day in order of hours
        schedule_list = []
        for day in all_days:
            schedule_list.append([schedule_dict[day].get(hour, "-") for hour in all_hours])

        context = {
            'hours': all_hours,
            'days_schedule': list(zip(all_days, schedule_list)),  # [(day, [courses])]
            'skipped_courses': skipped_courses
        }
        return render(request, 'App/timetable.html', context)

    return render(request, 'App/upload.html')

