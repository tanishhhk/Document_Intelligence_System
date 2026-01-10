# New service: app/services/video_generator.py

from app.services.llm import generate_answer
from elevenlabs import generate, save
from moviepy.editor import *
import os

class VideoGenerator:
    
    def __init__(self):
        self.output_dir = "generated_videos"
        os.makedirs(self.output_dir, exist_ok=True)
    
    async def generate_document_video(self, document_id: str, db):
        """Main function to generate video from document"""
        
        # Step 1: Generate comprehensive summary
        summary = await self._generate_summary(document_id, db)
        
        # Step 2: Generate voice narration
        audio_path = await self._generate_audio(summary)
        
        # Step 3: Extract key points
        key_points = await self._extract_key_points(summary)
        
        # Step 4: Generate visuals
        slides = await self._create_slides(key_points)
        
        # Step 5: Combine into video
        video_path = await self._create_video(slides, audio_path)
        
        return video_path
    
    async def _generate_summary(self, document_id, db):
        """Generate comprehensive summary using Gemini"""
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).all()
        
        full_text = "\n\n".join([c.chunk_text for c in chunks])
        
        prompt = f"""
        Create a comprehensive 2-minute video script summarizing this document.
        Make it educational, engaging, and easy to understand.
        Format as natural speech with clear sections.
        
        Document:
        {full_text}
        """
        
        summary = generate_answer("", prompt)
        return summary
    
    async def _generate_audio(self, text: str):
        """Generate voice narration using ElevenLabs"""
        audio = generate(
            text=text,
            voice="Rachel",
            model="eleven_monolingual_v1"
        )
        
        audio_path = f"{self.output_dir}/narration.mp3"
        save(audio, audio_path)
        return audio_path
    
    async def _extract_key_points(self, summary: str):
        """Extract main points for visual slides"""
        prompt = f"""
        Extract 5-7 key points from this summary.
        Return as a JSON array of strings.
        Each point should be concise (max 15 words).
        
        Summary: {summary}
        """
        
        # Get key points from AI
        response = generate_answer("", prompt)
        # Parse JSON response
        import json
        key_points = json.loads(response)
        return key_points
    
    async def _create_slides(self, key_points: list):
        """Create visual slides for each point"""
        slides = []
        
        for i, point in enumerate(key_points):
            # Create slide with text
            bg = ColorClip(
                size=(1920, 1080), 
                color=(30, 30, 50), 
                duration=5
            )
            
            txt = TextClip(
                point,
                fontsize=60,
                color='white',
                size=(1600, None),
                method='caption'
            ).set_position('center').set_duration(5)
            
            slide = CompositeVideoClip([bg, txt])
            slides.append(slide)
        
        return slides
    
    async def _create_video(self, slides: list, audio_path: str):
        """Combine slides and audio into final video"""
        # Concatenate all slides
        video = concatenate_videoclips(slides, method="compose")
        
        # Add audio
        audio = AudioFileClip(audio_path)
        video = video.set_audio(audio)
        
        # Export
        output_path = f"{self.output_dir}/summary_{int(time.time())}.mp4"
        video.write_videofile(
            output_path, 
            fps=24,
            codec='libx264',
            audio_codec='aac'
        )
        
        return output_path