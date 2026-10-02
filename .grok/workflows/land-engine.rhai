let meta = #{
    name: "land-engine",
    description: "Develop the Scot-LAND parcel-rent formula, test it with Henry George, Adam Smith, and a hostile economist, and record the result.",
    when_to_use: "Build the land-rent engine. Writes docs/ENGINE.md and docs/engine/LOG.md. Does not change the live calculator or the public pounds.",
    phases: [
        #{ title: "Read", detail: "The formula that is live today" },
        #{ title: "Specialists", detail: "Use, area, location, quality, tests" },
        #{ title: "Formula", detail: "One rent for every parcel" },
        #{ title: "Classical", detail: "Henry George and Adam Smith" },
        #{ title: "Revise", detail: "Answer George and Smith" },
        #{ title: "Economist", detail: "A hostile modern reading" },
        #{ title: "Settle", detail: "Answer the economist" },
        #{ title: "Record", detail: "ENGINE.md and the log" },
    ],
};

fn text_of(r, key) {
    if r == () {
        return "";
    }
    if r.success != true {
        return "";
    }
    if r.output == () {
        return "";
    }
    let v = r.output[key];
    if v == () {
        return "";
    }
    if type_of(v) != "string" {
        return "";
    }
    v.trim();
    return v;
}

fn passed_of(r) {
    if r == () {
        return false;
    }
    if r.success != true {
        return false;
    }
    if r.output == () {
        return false;
    }
    return r.output.passed == true;
}

let repo = "C:/Projects/scot-land";

let reader_schema = #{
    "type": "object",
    "required": ["live_formula", "unused_land_uses", "checks"],
    "properties": #{
        "live_formula": #{ "type": "string" },
        "unused_land_uses": #{ "type": "string" },
        "checks": #{ "type": "string" },
    },
};

let specialist_schema = #{
    "type": "object",
    "required": ["topic", "method", "sources", "gap"],
    "properties": #{
        "topic": #{ "type": "string" },
        "method": #{ "type": "string" },
        "sources": #{
            "type": "array",
            "maxItems": 8,
            "items": #{ "type": "string" },
        },
        "gap": #{ "type": "string" },
    },
};

let formula_schema = #{
    "type": "object",
    "required": ["formula", "steps", "rejected"],
    "properties": #{
        "formula": #{ "type": "string" },
        "steps": #{
            "type": "array",
            "maxItems": 12,
            "items": #{ "type": "string" },
        },
        "rejected": #{ "type": "string" },
    },
};

let classical_schema = #{
    "type": "object",
    "required": ["author", "passed", "failed_sentence", "note"],
    "properties": #{
        "author": #{ "type": "string" },
        "passed": #{ "type": "boolean" },
        "failed_sentence": #{ "type": "string" },
        "note": #{ "type": "string" },
    },
};

let economist_schema = #{
    "type": "object",
    "required": ["objections", "unresolved"],
    "properties": #{
        "objections": #{
            "type": "array",
            "maxItems": 8,
            "items": #{
                "type": "object",
                "required": ["attack", "answer"],
                "properties": #{
                    "attack": #{ "type": "string" },
                    "answer": #{ "type": "string" },
                },
            },
        },
        "unresolved": #{ "type": "string" },
    },
};

let rules = "";
rules += "Rules you must keep: the charge is the yearly rent of the whole registered parcel. ";
rules += "The building stays with the person who made it. Floor area is not the thing charged and is not shown. ";
rules += "Do not scrape Zoopla, Rightmove, ESPC, OnTheMarket, or the Scottish Assessors portal. ";
rules += "Do not edit backend/, frontend/, or data/config/agr.yaml. ";
rules += "Do not change the public pounds. Glasgow G1 1BL stays near £8,001 on about 760 square metres. ";
rules += "Wick KW1 4AA stays near £8.28 on about 1,897 square metres. ";
rules += "The full Annual Ground Rent is already chosen in docs/DECISION.md. Do not reopen that choice. ";
rules += "Hope value stays excluded unless you only record the difference. ";

phase("Read");
let reader_prompt = "";
reader_prompt += "You are the reader for the Scot-LAND land engine. Read the files before you answer. ";
reader_prompt += "Repo: ";
reader_prompt += repo;
reader_prompt += ". Read backend/agr/valuation.py, data/config/agr.yaml, and docs/DECISION.md. ";
reader_prompt += rules;
reader_prompt += "Describe the formula that is live today in live_formula. ";
reader_prompt += "List the signed land-use values that the live path does not apply to each parcel, in unused_land_uses. ";
reader_prompt += "Put the Glasgow and Wick checks in checks. Do not propose a new formula.";
let reader = agent(reader_prompt, #{
    label: "reader",
    capability_mode: "read-only",
    output_schema: reader_schema,
});
log("Reader finished.");

phase("Specialists");
let topics = [
    #{
        id: "use-rights",
        label: "Use rights",
        task: "Class each Scottish parcel by its existing authorised use, using open or licensed sources only. A weak class is still a class, with a confidence. Do not finish by saying the use is unknown. Name the sources and how the parcel is joined to them.",
    },
    #{
        id: "area",
        label: "Area",
        task: "Turn the whole land area into a rent. A field is rate times area. A house is a stance up to a normal plot at the location rate, and the rest of the parcel at a lower land rate. Poor land can be zero. A shared title is the rent of the whole piece, not one household bill. Do not treat garden as rooms.",
    },
    #{
        id: "location",
        label: "Location",
        task: "Find the finest legal location grain for the rent. Council is the signed grain today. Name any open or licensed dataset that can tighten it. If none can, say the council remains the grain and name the dataset that would be next.",
    },
    #{
        id: "quality",
        label: "Productive quality",
        task: "Band farmland, forestry, and hill by a free land-capability source if one can be used. Land with no surplus uses the zero marginal rent already in the config. Say how a parcel is split into capable land and marginal land.",
    },
    #{
        id: "tests",
        label: "Test set",
        task: "Define a house, a tenement, a shop, a field, a hill, and a vacant urban site. For each, say which inputs the formula needs and what a wrong answer would look like. Use Glasgow G1 1BL and Wick KW1 4AA as the two figures that must stay unchanged until the formula is accepted.",
    },
];

let jobs = [];
for topic in topics {
    let prompt = "";
    prompt += "You are a specialist for the Scot-LAND land engine. Read ";
    prompt += repo;
    prompt += "/docs/DECISION.md and ";
    prompt += repo;
    prompt += "/data/config/agr.yaml before you answer. Search for current open data. Do not edit any file. ";
    prompt += rules;
    prompt += "Your topic is ";
    prompt += topic.label;
    prompt += ". ";
    prompt += topic.task;
    prompt += " Set topic to ";
    prompt += topic.label;
    prompt += ". Put the workable method in method. Put source names in sources. Put the remaining weakness in gap. A method that gives up is not acceptable.";
    jobs.push(#{
        prompt: prompt,
        label: topic.id,
        capability_mode: "all",
        output_schema: specialist_schema,
    });
}
let specialist_results = parallel(jobs);
log("Specialists finished.");

phase("Formula");
let draft_prompt = "";
draft_prompt += "You are the lead for the Scot-LAND land engine. Write one formula that takes a parcel and returns a yearly land rent. ";
draft_prompt += "Use the reader and the specialists below. Do not edit files. ";
draft_prompt += rules;
draft_prompt += "Reader live formula: ";
draft_prompt += text_of(reader, "live_formula");
draft_prompt += " Unused land uses: ";
draft_prompt += text_of(reader, "unused_land_uses");
draft_prompt += " Checks: ";
draft_prompt += text_of(reader, "checks");
draft_prompt += " Specialists: ";
for r in specialist_results {
    if r != () && r.success && r.output != () {
        draft_prompt += json_encode(r.output);
        draft_prompt += " ";
    }
}
draft_prompt += "Return the formula in plain sentences in formula. Return the ordered steps in steps. Put what you refused, and why, in rejected.";
let draft = agent(draft_prompt, #{
    label: "lead-draft",
    capability_mode: "read-only",
    output_schema: formula_schema,
});
let formula = text_of(draft, "formula");
log("Draft formula finished.");

phase("Classical");
let george_prompt = "";
george_prompt += "You are the Henry George check for the Scot-LAND land engine. Read ";
george_prompt += repo;
george_prompt += "/docs/DECISION.md. Do not edit files. Do not paste a book. Do not say the author endorses the site. Do not invent a new tax. ";
george_prompt += rules;
george_prompt += "Formula: ";
george_prompt += formula;
george_prompt += " Set author to Henry George. Set passed true only if the figure is the rent of the land, the building is outside it, the maker keeps the improvement, and the rent is public because the public made the location valuable. ";
george_prompt += "A vacant site still has a land rent in your test. The signed config excludes hope value and uses the existing authorised use. Flag that difference in note. Do not switch the signed rule. ";
george_prompt += "If passed is false, put the failing sentence in failed_sentence. If passed is true, leave failed_sentence empty.";
let smith_prompt = "";
smith_prompt += "You are the Adam Smith check for the Scot-LAND land engine. Read ";
smith_prompt += repo;
smith_prompt += "/docs/DECISION.md. Do not edit files. Do not paste a book. Do not say the author endorses the site. Do not demand that every other tax be abolished. ";
smith_prompt += rules;
smith_prompt += "Formula: ";
smith_prompt += formula;
smith_prompt += " Set author to Adam Smith. Set passed true only if this is ground-rent, wages and trade and the building are not taxed, and the return on an improvement stays with the person who paid for it. ";
smith_prompt += "A charge on ground-rent should not raise the price of the produce of labour. ";
smith_prompt += "If passed is false, put the failing sentence in failed_sentence. If passed is true, leave failed_sentence empty. Record in note that you do not require every other tax to be replaced, and that this site nonetheless states the full Annual Ground Rent.";
let classical = parallel([
    #{
        prompt: george_prompt,
        label: "henry-george",
        capability_mode: "read-only",
        output_schema: classical_schema,
    },
    #{
        prompt: smith_prompt,
        label: "adam-smith",
        capability_mode: "read-only",
        output_schema: classical_schema,
    },
]);
let george = classical[0];
let smith = classical[1];
log("George and Smith finished.");

phase("Revise");
let revise_prompt = "";
revise_prompt += "You are the lead for the Scot-LAND land engine. Revise the formula. Do not edit files. ";
revise_prompt += rules;
revise_prompt += "Current formula: ";
revise_prompt += formula;
revise_prompt += " Henry George passed: ";
if passed_of(george) {
    revise_prompt += "yes. ";
} else {
    revise_prompt += "no. ";
}
revise_prompt += "George note: ";
revise_prompt += text_of(george, "note");
revise_prompt += " George failing sentence: ";
revise_prompt += text_of(george, "failed_sentence");
revise_prompt += " Adam Smith passed: ";
if passed_of(smith) {
    revise_prompt += "yes. ";
} else {
    revise_prompt += "no. ";
}
revise_prompt += "Smith note: ";
revise_prompt += text_of(smith, "note");
revise_prompt += " Smith failing sentence: ";
revise_prompt += text_of(smith, "failed_sentence");
revise_prompt += "Change the formula so a failing sentence is no longer true. Do not average George and Smith. Do not reopen the choice of the full Annual Ground Rent. Keep hope value excluded and record George's vacant-land test as a later decision. Return the revised formula.";
let revised = agent(revise_prompt, #{
    label: "lead-revise",
    capability_mode: "read-only",
    output_schema: formula_schema,
});
let revised_formula = text_of(revised, "formula");
if revised_formula != "" {
    formula = revised_formula;
}
log("Formula revised after George and Smith.");

phase("Economist");
let econ_prompt = "";
econ_prompt += "You are a hostile economist reviewing the Scot-LAND formula. You did not write it. Read ";
econ_prompt += repo;
econ_prompt += "/docs/DECISION.md and backend/agr/valuation.py. Do not edit files. ";
econ_prompt += rules;
econ_prompt += "Formula: ";
econ_prompt += formula;
econ_prompt += " Attack only these faults if they are really in the formula: garden counted as rooms, a tenement compared with one person, a rural house charged as a field, a city field charged as a house, house prices treated as if they were already land rent, the national pool treated as a sum of parcels, a scraped portal, or a silent change to the signed-off figures. ";
econ_prompt += "For each real fault, put the attack and the correction in objections. Put anything you cannot correct without a new signed number in unresolved. Do not invent a different tax.";
let economist = agent(econ_prompt, #{
    label: "economist",
    capability_mode: "read-only",
    output_schema: economist_schema,
});
log("Economist finished.");

phase("Settle");
let settle_prompt = "";
settle_prompt += "You are the lead for the Scot-LAND land engine. Produce the formula to record. Do not edit files. ";
settle_prompt += rules;
settle_prompt += "Formula: ";
settle_prompt += formula;
settle_prompt += " Economist: ";
if economist != () && economist.success && economist.output != () {
    settle_prompt += json_encode(economist.output);
}
settle_prompt += " Answer each objection inside the formula. If an objection needs a new signed number, leave the public pounds unchanged and say whose decision it is. Return the final formula in formula, the ordered steps in steps, and what you refused in rejected.";
let settled = agent(settle_prompt, #{
    label: "lead-settle",
    capability_mode: "read-only",
    output_schema: formula_schema,
});
let final_formula = text_of(settled, "formula");
if final_formula != "" {
    formula = final_formula;
}
log("Formula settled.");

phase("Record");
let record_prompt = "";
record_prompt += "You are the scribe for the Scot-LAND land engine. Write the record. Today is 2 October 2026. Repo: ";
record_prompt += repo;
record_prompt += ". ";
record_prompt += rules;
record_prompt += "Create docs/ENGINE.md and docs/engine/LOG.md. Update only the opening of docs/STATUS.md so it points at those two files and says the public pounds are unchanged. ";
record_prompt += "Do not edit backend/, frontend/, data/config/agr.yaml, or the live site. ";
record_prompt += "If the formula text is empty, write the log saying this run did not return a formula, and do not invent one. ";
record_prompt += "ENGINE.md is in plain sentences: the charge, the formula, use, area, location, quality, Henry George, Adam Smith, objections already tested, what is not claimed, and the Glasgow and Wick checks as unchanged. ";
record_prompt += "LOG.md is append-only. One entry each for the reader, each specialist, Henry George, Adam Smith, and the economist. Each entry has Decision, Reason, Source, Rejected, and Would fail if. ";
record_prompt += "Final formula: ";
record_prompt += formula;
record_prompt += " Rejected: ";
record_prompt += text_of(settled, "rejected");
record_prompt += " George note: ";
record_prompt += text_of(george, "note");
record_prompt += " George failing sentence: ";
record_prompt += text_of(george, "failed_sentence");
record_prompt += " Smith note: ";
record_prompt += text_of(smith, "note");
record_prompt += " Smith failing sentence: ";
record_prompt += text_of(smith, "failed_sentence");
record_prompt += " Economist unresolved: ";
record_prompt += text_of(economist, "unresolved");
record_prompt += " Reader: ";
record_prompt += text_of(reader, "live_formula");
record_prompt += " Specialists: ";
for r in specialist_results {
    if r != () && r.success && r.output != () {
        record_prompt += json_encode(r.output);
        record_prompt += " ";
    }
}
if economist != () && economist.success && economist.output != () {
    record_prompt += " Economist object: ";
    record_prompt += json_encode(economist.output);
}
let recorded = agent(record_prompt, #{
    label: "scribe",
    capability_mode: "read-write",
});
log("Record written.");

let summary = "Land engine recorded.";
if formula == "" {
    summary = "Land engine run finished without a formula.";
}
if recorded == () || recorded.success != true {
    summary = "Land engine formula was drafted but the record agent did not finish.";
}
complete(#{
    summary: summary,
    formula_present: formula != "",
});
