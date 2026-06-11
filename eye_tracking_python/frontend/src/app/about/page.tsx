import Link from "next/link";
import DisclaimerBox from "@/components/DisclaimerBox";
import FounderPhoto from "@/components/FounderPhoto";
import { FOUNDER } from "@/lib/constants";

export const metadata = {
  title: "About — Ocula",
};

export default function AboutPage() {
  return (
    <>
      {/* Story */}
      <section className="about-hero">
        <div className="container" style={{ maxWidth: 760 }}>
          <span className="eyebrow">About Ocula</span>
          <h1>Cleaner eye-movement data, for everyone studying it.</h1>
          <div className="prose mt-2">
            <p>
              Ocula began as a student research project exploring how eye movement
              data could be collected in a more accessible, structured, and
              user-friendly way. Most eye-tracking research relies on specialized
              hardware and lab setups. Ocula asks a smaller, more practical
              question: how much can you do with an ordinary webcam, careful task
              design, and honest data hygiene?
            </p>
            <p>
              The result is a calm, guided experience — a few short dot-following
              activities that record how the eyes respond, and a clear summary you
              can review and save. Nothing about Ocula tries to make a medical
              judgment. The goal is good data and a good experience.
            </p>
          </div>
        </div>
      </section>

      {/* Founder */}
      <section className="section section-soft section-line">
        <div className="container">
          <span className="eyebrow">The founder</span>
          <h2 style={{ maxWidth: "20ch", marginBottom: 28 }}>
            Built by a student researcher interested in medicine, AI, and movement
            disorders.
          </h2>

          <div className="founder">
            <div className="founder-photo-wrap">
              <FounderPhoto
                alt={`${FOUNDER.name}, founder of Ocula`}
                initials={FOUNDER.initials}
              />
              <div className="founder-caption">
                <div className="name">{FOUNDER.name}</div>
                <div className="role">{FOUNDER.role}</div>
              </div>
            </div>

            <div className="prose">
              <p>
                I&apos;m {FOUNDER.name}, a student researcher at Thomas Jefferson
                High School for Science and Technology. I&apos;m drawn to the
                intersection of medicine, machine learning, and accessible research
                tools — and Ocula sits right in the middle of it.
              </p>
              <p>
                My work so far spans both biology and computer vision. I&apos;ve
                designed and run controlled experiments — measuring photosynthesis
                with spectrophotometry, analyzing field data with statistical
                models — and I&apos;ve built image-processing and neural-network
                projects (Python, TensorFlow/Keras, CNNs), including AI-based
                species identification from imagery. Through my school&apos;s
                Cardiology &amp; Neurobiology Society and a cancer research club, I
                became curious about how the body produces movement, and how subtle
                and informative that movement can be.
              </p>
              <p>
                I also captain my school&apos;s robotics team, where I&apos;ve
                learned that the hard part of any technical project is usually not
                the model — it&apos;s the careful, unglamorous work of collecting
                clean data and being honest about what it can and can&apos;t say.
                Ocula grew out of that mindset, and a simple question:{" "}
                <strong>
                  can ordinary camera-based activities collect cleaner, more
                  structured eye-movement data for future neurological research?
                </strong>
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Motivation */}
      <section className="section">
        <div className="container grid grid-2" style={{ gap: 52, alignItems: "start" }}>
          <div>
            <span className="eyebrow">Why I&apos;m building it</span>
            <h2>Make the tools accessible. Keep the science honest.</h2>
          </div>
          <div className="prose">
            <p>
              I care about making research tools more accessible. A lot of
              eye-tracking work depends on equipment most people will never have, so
              I wanted to see how far a webcam, thoughtful task design, and good data
              practices could go.
            </p>
            <p>
              I&apos;m especially interested in Parkinson&apos;s disease and other
              movement-related conditions, where timing and eye control are studied
              closely. To be clear: my goal is <strong>not</strong> to diagnose
              anything. It&apos;s to build something clean and trustworthy that
              could, after proper validation and with clinician oversight, eventually
              help researchers and clinicians work with better data.
            </p>
          </div>
        </div>
      </section>

      {/* Research vision */}
      <section className="section section-soft section-line">
        <div className="container">
          <span className="eyebrow">Research vision</span>
          <h2 style={{ maxWidth: "24ch" }}>Where this could go — carefully.</h2>
          <div className="grid grid-2 mt-3" style={{ gap: 22 }}>
            <div className="card card-flat">
              <h3>Today</h3>
              <p className="small">
                Ocula collects structured eye-movement data during short activities
                and reports tracking quality and simple, friendly summaries.
              </p>
            </div>
            <div className="card card-flat">
              <h3>What researchers study</h3>
              <p className="small">
                Eye tracking is an active research signal. Parkinson&apos;s-related
                research may involve response timing, saccades, fixation stability,
                and smooth pursuit.
              </p>
            </div>
            <div className="card card-flat">
              <h3>What it would take</h3>
              <p className="small">
                Any future prognosis-support tool would require clinical datasets,
                independent validation, regulatory review, and oversight by
                qualified healthcare professionals.
              </p>
            </div>
            <div className="card card-flat">
              <h3>The principle</h3>
              <p className="small">
                Ocula is designed to support research workflows — not to replace
                clinical evaluation, and not to make medical claims.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Disclaimer */}
      <section className="section">
        <div className="container" style={{ maxWidth: 820 }}>
          <DisclaimerBox />
          <div className="row mt-3">
            <Link className="btn btn-primary" href="/signup">
              Create your account
            </Link>
            <Link className="btn btn-ghost" href="/research">
              Read the research page
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
